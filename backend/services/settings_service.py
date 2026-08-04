# backend/services/settings_service.py
"""
Account security logic: active sessions, password changes, 2FA toggle.
HTTP-agnostic like task_service.py — routers/settings.py just translates
this into responses and status codes.
"""
from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from models.user_session import UserSession
from services.auth_service import hash_password, verify_password


class SessionNotFoundError(Exception):
    def __init__(self, session_id: UUID):
        self.session_id = session_id
        super().__init__(f"Session {session_id} not found")


def hash_token(raw_token: str) -> str:
    """Same digest auth_service uses for refresh-token lookups — duplicated
    here (rather than importing a private helper) so this file doesn't
    depend on auth_service's internals. Keep in sync if that ever changes."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

async def list_sessions(db: AsyncSession, *, user_id: UUID) -> list[UserSession]:
    result = await db.execute(
        select(UserSession)
        .where(UserSession.user_id == user_id, UserSession.is_active.is_(True))
        .order_by(UserSession.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_session(db: AsyncSession, *, user_id: UUID, session_id: UUID) -> None:
    result = await db.execute(
        select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise SessionNotFoundError(session_id)

    session.is_active = False
    await db.commit()


async def revoke_other_sessions(
    db: AsyncSession, *, user_id: UUID, keep_token_hash: str | None
) -> int:
    """Kills every active session except the one making this request.
    Returns the count so the frontend can confirm ('Signed out of 3 devices')."""
    conditions = [UserSession.user_id == user_id, UserSession.is_active.is_(True)]
    if keep_token_hash:
        conditions.append(UserSession.token_hash != keep_token_hash)

    result = await db.execute(select(UserSession).where(*conditions))
    sessions = list(result.scalars().all())

    for session in sessions:
        session.is_active = False
    await db.commit()  # one round trip, not one commit per session

    return len(sessions)


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------

async def change_password(
    db: AsyncSession, *, user: User, current_password: str, new_password: str
) -> None:
    if not user.password_hash:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This account signs in via OAuth and doesn't have a password to change",
        )

    if not await verify_password(current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")

    user.password_hash = await hash_password(new_password)
    await db.commit()


# ---------------------------------------------------------------------------
# Two-factor
# ---------------------------------------------------------------------------

async def set_two_factor(db: AsyncSession, *, user: User, enabled: bool) -> str | None:
    """
    Tracks on/off state and generates a secret when enabling. There's no
    TOTP verification loop yet (needs a QR-code step on the frontend) —
    this deliberately doesn't pretend to be a finished 2FA flow, just the
    piece of it that has somewhere to live right now.
    """
    if enabled:
        user.two_fa_secret = secrets.token_hex(20)
        user.two_fa_enabled = True
    else:
        user.two_fa_secret = None
        user.two_fa_enabled = False

    await db.commit()
    return user.two_fa_secret if enabled else None