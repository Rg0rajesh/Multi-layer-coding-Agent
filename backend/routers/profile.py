# backend/routers/profile.py
"""
Profile page's backend — viewing and editing the current user's identity
fields (name, bio, links, avatar). Password, sessions, and 2FA are account
security concerns and live in routers/settings.py instead.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from services.auth_service import get_current_user
from services.profile_service import update_profile

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


# ---------------------------------------------------------------- schemas

class ProfileOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    display_name: str | None
    avatar_url: str | None
    bio: str | None
    website_url: str | None
    github_url: str | None
    twitter_handle: str | None
    plan: str
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=100)
    bio: str | None = Field(None, max_length=500)
    avatar_url: str | None = Field(None, max_length=2048)
    website_url: str | None = Field(None, max_length=2048)
    github_url: str | None = Field(None, max_length=2048)
    twitter_handle: str | None = Field(None, max_length=50)

    def to_patch_dict(self) -> dict:
        # PATCH semantics — only fields the client actually sent get touched,
        # same convention as TaskUpdate in routers/tasks.py.
        return self.model_dump(exclude_unset=True)


# ----------------------------------------------------------------- routes

@router.get("", response_model=ProfileOut)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("", response_model=ProfileOut)
async def update_profile_endpoint(
    payload: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await update_profile(db, user=current_user, data=payload.to_patch_dict())