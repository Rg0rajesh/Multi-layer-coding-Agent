
# backend/routers/team.py
"""
Team management — members, roles, permissions matrix. Every endpoint
starts with get_team_with_membership, so "team doesn't exist" and "you're
not on this team" both come back as a 404. Role checks (require_role)
happen after that, as a 403.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.team import Team, TeamMember
from models.user import User
from services import team_service
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])

# owner is never assigned directly — it only changes via transfer_ownership
VALID_ROLES = {"viewer", "editor", "admin"}


# ---------------------------------------------------------------- schemas

class TeamCreate(BaseModel):
    name: str = Field(..., max_length=255)
    logo_url: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    logo_url: str | None = None
    default_agent_config: dict | None = None

    def to_patch_dict(self) -> dict:
        return self.model_dump(exclude_unset=True)


class TeamOut(BaseModel):
    id: UUID
    name: str
    logo_url: str | None
    subdomain: str | None
    owner_id: UUID
    default_agent_config: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    avatar_url: str | None
    role: str
    status: str
    joined_at: datetime


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = "viewer"


class UpdateMemberRoleRequest(BaseModel):
    role: str


class TransferOwnershipRequest(BaseModel):
    new_owner_member_id: UUID


# ------------------------------------------------------------- helpers

async def _get_membership(db: AsyncSession, team_id: UUID, user: User) -> tuple[Team, TeamMember]:
    try:
        return await team_service.get_team_with_membership(db, team_id=team_id, user_id=user.id)
    except team_service.TeamNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")


def _require_role(membership: TeamMember, minimum: str) -> None:
    try:
        team_service.require_role(membership, minimum)
    except team_service.PermissionDeniedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


def _member_out(member: TeamMember, user: User) -> MemberOut:
    return MemberOut(
        id=member.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        role=member.role,
        status=member.status,
        joined_at=member.joined_at,
    )


# ----------------------------------------------------------------- routes
# Teams

@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await team_service.create_team(db, owner_id=current_user.id, name=body.name, logo_url=body.logo_url)


@router.get("", response_model=list[TeamOut])
async def list_my_teams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await team_service.list_teams_for_user(db, user_id=current_user.id)


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(
    team_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    team, _ = await _get_membership(db, team_id, current_user)
    return team


@router.patch("/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: UUID,
    body: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    team, membership = await _get_membership(db, team_id, current_user)
    _require_role(membership, "admin")
    return await team_service.update_team(db, team=team, data=body.to_patch_dict())


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    team, membership = await _get_membership(db, team_id, current_user)
    _require_role(membership, "owner")
    await team_service.delete_team(db, team=team)


# ----------------------------------------------------------------- routes
# Members

@router.get("/{team_id}/members", response_model=list[MemberOut])
async def list_members(
    team_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_membership(db, team_id, current_user)  # any member can see the roster
    rows = await team_service.list_members(db, team_id=team_id)
    return [_member_out(member, user) for member, user in rows]


@router.post("/{team_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def invite_member(
    team_id: UUID,
    body: InviteMemberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, membership = await _get_membership(db, team_id, current_user)
    _require_role(membership, "admin")

    if body.role not in VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"role must be one of {sorted(VALID_ROLES)}")

    try:
        member = await team_service.add_member(db, team_id=team_id, email=body.email, role=body.role)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    user = await db.get(User, member.user_id)
    return _member_out(member, user)


@router.patch("/{team_id}/members/{member_id}", response_model=MemberOut)
async def update_member_role(
    team_id: UUID,
    member_id: UUID,
    body: UpdateMemberRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, membership = await _get_membership(db, team_id, current_user)
    _require_role(membership, "admin")

    if body.role not in VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"role must be one of {sorted(VALID_ROLES)}")

    try:
        target = await team_service.get_member(db, team_id=team_id, member_id=member_id)
    except team_service.MemberNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")

    # An admin can't hand out a role higher than their own, and can't
    # touch the owner's role at all (blocked in the service layer too).
    if team_service.ROLE_RANK[body.role] > team_service.ROLE_RANK[membership.role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Can't grant a role higher than your own")

    try:
        updated = await team_service.update_member_role(db, member=target, new_role=body.role)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    user = await db.get(User, updated.user_id)
    return _member_out(updated, user)


@router.delete("/{team_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, membership = await _get_membership(db, team_id, current_user)

    try:
        target = await team_service.get_member(db, team_id=team_id, member_id=member_id)
    except team_service.MemberNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")

    # Leaving the team yourself doesn't need admin rights; removing
    # someone else does.
    if target.user_id != current_user.id:
        _require_role(membership, "admin")

    try:
        await team_service.remove_member(db, member=target)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/{team_id}/transfer-ownership", response_model=TeamOut)
async def transfer_ownership(
    team_id: UUID,
    body: TransferOwnershipRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    team, membership = await _get_membership(db, team_id, current_user)
    _require_role(membership, "owner")

    try:
        new_owner = await team_service.get_member(db, team_id=team_id, member_id=body.new_owner_member_id)
    except team_service.MemberNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")

    try:
        await team_service.transfer_ownership(db, team=team, current_owner=membership, new_owner=new_owner)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    await db.refresh(team)
    return team