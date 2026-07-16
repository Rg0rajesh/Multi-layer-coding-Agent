# backend/services/auth_service.py
"""
Handles the actual auth logic: password hashing, JWT issuance, refresh-token
rotation, and the GitHub/Google OAuth exchange. routers/auth.py stays thin
and just wires HTTP <-> these functions.
"""
from __future__ import annotations

import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.user import User
from models.user_session import UserSession

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Passwords
# ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++    

async def hash_password(raw: str) -> str:
    # bcrypt is intentionally slow (~100ms) — never block the event loop with it
    return await run_in_threadpool(pwd_context.hash, raw)


async def verify_password(raw: str, hashed: str) -> bool:
    return await run_in_threadpool(pwd_context.verify, raw, hashed)


# ***************************************************************************
# JWT access tokens
#***************************************************************************    

def create_access_token(user_id: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expires, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """Returns the user id encoded in the token, or raises 401."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    return payload["sub"]


# ***************************************************************************
# Refresh tokens — opaque random string, only the SHA-256 digest hits the DB.
#
# We deliberately don't bcrypt these: bcrypt is slow on purpose so brute-
# forcing a low-entropy human password is expensive, but a refresh token is
# already 384 bits of secrets.token_urlsafe output — there's nothing to
# brute-force. Bcrypt-hashing it would also mean no indexed lookup: you'd
# have to pull every active session for a user and bcrypt-compare each one
# (O(n) per refresh, and bcrypt-slow on top of that). SHA-256 gives a
# deterministic digest we can index and look up directly (O(log n) on the
# unique btree index already defined on token_hash).
# ***************************************************************************

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_refresh_token(
    db: AsyncSession, user_id: str, device_info: str | None, ip_address: str | None
) -> str:
    raw_token = secrets.token_urlsafe(48)
    session = UserSession(
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        device_info=device_info,
        ip_address=ip_address,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    await db.commit()
    return raw_token


async def rotate_refresh_token(
    db: AsyncSession, raw_token: str, device_info: str | None, ip_address: str | None
) -> tuple[User, str]:
    """Validates a refresh token, kills it, and issues a new one (rotation).
    Returns (user, new_raw_token)."""
    token_hash = _hash_token(raw_token)

    result = await db.execute(
        select(UserSession).where(
            UserSession.token_hash == token_hash,
            UserSession.is_active.is_(True),
        )
    )
    session = result.scalar_one_or_none()

    if session is None or session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token invalid or expired")

    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer active")

    # Rotate: kill the old session, issue a fresh one. Stops a stolen
    # refresh token from being replayed indefinitely once it's used once.
    session.is_active = False
    new_token = await issue_refresh_token(db, str(user.id), device_info, ip_address)
    await db.commit()

    return user, new_token


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    token_hash = _hash_token(raw_token)
    result = await db.execute(select(UserSession).where(UserSession.token_hash == token_hash))
    session = result.scalar_one_or_none()
    if session:
        session.is_active = False
        await db.commit()


# ***************************************************************************
# OAuth — GitHub & Google
# ************ ***********************************************************************

async def exchange_github_code(code: str) -> dict:
    """Trades an OAuth code for the GitHub profile (and primary verified email)."""
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "GitHub rejected that code")

        auth_header = {"Authorization": f"Bearer {access_token}"}

        # Profile + email list are independent calls — fire them together
        # instead of waiting on one before starting the other.
        profile_resp, emails_resp = await asyncio.gather(
            client.get(GITHUB_USER_URL, headers=auth_header),
            client.get(GITHUB_EMAILS_URL, headers=auth_header),
        )
        profile_resp.raise_for_status()
        emails_resp.raise_for_status()

    profile = profile_resp.json()
    primary_email = next(
        (e["email"] for e in emails_resp.json() if e.get("primary") and e.get("verified")),
        profile.get("email"),
    )

    return {
        "provider_id": str(profile["id"]),
        "email": primary_email,
        "full_name": profile.get("name") or profile.get("login"),
        "avatar_url": profile.get("avatar_url"),
    }


async def exchange_google_code(code: str, redirect_uri: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google rejected that code")

        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        userinfo_resp.raise_for_status()

    profile = userinfo_resp.json()
    return {
        "provider_id": profile["sub"],
        "email": profile.get("email"),
        "full_name": profile.get("name"),
        "avatar_url": profile.get("picture"),
    }


async def find_or_create_oauth_user(db: AsyncSession, provider: str, profile: dict) -> User:
    """provider is 'github' or 'google'. Matches by provider id first (stable),
    falls back to email so someone who signed up with a password can link
    an OAuth provider later without ending up with two accounts."""
    id_column = User.github_id if provider == "github" else User.google_id

    result = await db.execute(select(User).where(id_column == profile["provider_id"]))
    user = result.scalar_one_or_none()

    if not user and profile.get("email"):
        result = await db.execute(select(User).where(User.email == profile["email"]))
        user = result.scalar_one_or_none()

    if user:
        setattr(user, f"{provider}_id", profile["provider_id"])
    else:
        user = User(
            email=profile["email"] or f"{provider}_{profile['provider_id']}@no-email.local",
            full_name=profile.get("full_name") or "New User",
            avatar_url=profile.get("avatar_url"),
            is_verified=True,  # the OAuth provider already verified this email
        )
        setattr(user, f"{provider}_id", profile["provider_id"])
        db.add(user)

    await db.commit()
    await db.refresh(user)
    return user