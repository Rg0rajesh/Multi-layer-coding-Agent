
# backend/routers/settings.py
"""
Settings > Security backend: active sessions, password changes, 2FA
toggle. Alert rules live in routers/logs.py instead — they're really an
Error Logs concern, not an account setting.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from services import settings_service
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

REFRESH_COOKIE = "agentx_refresh"  # matches routers/auth.py


# ---------------------------------------------------------------- schemas

class SessionOut(BaseModel):
    id: UUID
    device_info: str | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime
    is_current: bool


class RevokeAllOut(BaseModel):
    revoked_count: int


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class TwoFactorRequest(BaseModel):
    enabled: bool


class TwoFactorOut(BaseModel):
    two_fa_enabled: bool
    secret: str | None = None  # only present right after enabling


# ------------------------------------------------------------- helpers

def _current_session_hash(request: Request) -> str | None:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    return settings_service.hash_token(raw_token) if raw_token else None


# ----------------------------------------------------------------- routes
# Sessions

@router.get("/sessions", response_model=list[SessionOut])
async def get_sessions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = await settings_service.list_sessions(db, user_id=current_user.id)
    current_hash = _current_session_hash(request)

    return [
        SessionOut(
            id=s.id,
            device_info=s.device_info,
            ip_address=s.ip_address,
            created_at=s.created_at,
            expires_at=s.expires_at,
            is_current=(s.token_hash == current_hash),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session_endpoint(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        await settings_service.revoke_session(db, user_id=current_user.id, session_id=session_id)
    except settings_service.SessionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")


@router.post("/sessions/revoke-others", response_model=RevokeAllOut)
async def revoke_other_sessions_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = await settings_service.revoke_other_sessions(
        db, user_id=current_user.id, keep_token_hash=_current_session_hash(request)
    )
    return RevokeAllOut(revoked_count=count)


# ----------------------------------------------------------------- routes
# Password + 2FA

@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password_endpoint(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await settings_service.change_password(
        db,
        user=current_user,
        current_password=body.current_password,
        new_password=body.new_password,
    )


@router.patch("/two-factor", response_model=TwoFactorOut)
async def toggle_two_factor(
    body: TwoFactorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    secret = await settings_service.set_two_factor(db, user=current_user, enabled=body.enabled)
    return TwoFactorOut(two_fa_enabled=current_user.two_fa_enabled, secret=secret)