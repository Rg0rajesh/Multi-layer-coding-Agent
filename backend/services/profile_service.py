# backend/services/profile_service.py
"""
Profile field updates. Deliberately tiny — there's no business logic here
beyond "apply the patch, save it." Kept as its own service (instead of
inlined in the router) so it's consistent with how task/auth updates work
elsewhere, and so it's trivial to unit test without a request context.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User


async def update_profile(db: AsyncSession, *, user: User, data: dict) -> User:
    for field, value in data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user