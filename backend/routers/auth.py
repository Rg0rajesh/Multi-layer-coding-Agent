# backend/routers/auth.py
"""
Auth endpoints: email/password register + login, refresh-token rotation,
logout, and GitHub/Google OAuth. All the real logic lives in
services/auth_service.py — this file just wires HTTP to it.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_COOKIE = "agentx_refresh"


# =======================================================================
# Request/response schemas
# ======================================================================

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OAuthCallbackRequest(BaseModel):
    code: str
    redirect_uri: str | None = None  # required for Google, ignored by GitHub


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str


# ........................................... ..................................................
# Small helpers shared by every endpoint that issues tokens
# ............................................................................................

def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,  # 30 days — keep in sync with settings.refresh_token_expire_days
        path="/api/v1/auth",
    )


async def _issue_tokens(db: AsyncSession, request: Request, response: Response, user: User) -> TokenResponse:
    access_token = auth_service.create_access_token(str(user.id))
    refresh_token = await auth_service.issue_refresh_token(
        db,
        str(user.id),
        request.headers.get("user-agent"),
        request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, refresh_token)

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return TokenResponse(
        access_token=access_token, user_id=str(user.id), email=user.email, full_name=user.full_name
    )


# ---------------------------------------------------------------------------
# Email / password
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "That email's already registered")

    user = User(
        email=body.email,
        full_name=body.full_name,
        password_hash=await auth_service.hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return await _issue_tokens(db, request, response, user)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Always run a verify, even for a nonexistent user, against a dummy hash —
    # otherwise "no such user" short-circuits faster than "wrong password"
    # and that timing difference leaks which emails are registered.
    password_hash = user.password_hash if (user and user.password_hash) else "$2b$12$" + "x" * 53
    valid = await auth_service.verify_password(body.password, password_hash)

    if not user or not valid or not user.password_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    return await _issue_tokens(db, request, response, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token present")

    user, new_token = await auth_service.rotate_refresh_token(
        db, raw_token, request.headers.get("user-agent"), request.client.host if request.client else None
    )
    _set_refresh_cookie(response, new_token)

    access_token = auth_service.create_access_token(str(user.id))
    return TokenResponse(
        access_token=access_token, user_id=str(user.id), email=user.email, full_name=user.full_name
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        await auth_service.revoke_refresh_token(db, raw_token)
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


# ///////////////////////////////////////////////////////////////////////
# OAuth
# //////////////////////////////////////////////////////////////////////

@router.post("/oauth/github", response_model=TokenResponse)
async def oauth_github(
    body: OAuthCallbackRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    profile = await auth_service.exchange_github_code(body.code)
    user = await auth_service.find_or_create_oauth_user(db, "github", profile)
    return await _issue_tokens(db, request, response, user)


@router.post("/oauth/google", response_model=TokenResponse)
async def oauth_google(
    body: OAuthCallbackRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    if not body.redirect_uri:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "redirect_uri is required for Google OAuth")

    profile = await auth_service.exchange_google_code(body.code, body.redirect_uri)
    user = await auth_service.find_or_create_oauth_user(db, "google", profile)
    return await _issue_tokens(db, request, response, user)