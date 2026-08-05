# backend/services/team_service.py
"""
Team CRUD + membership/role management. Kept HTTP-agnostic, same pattern
as task_service.py and output_service.py — routers/team.py translates
these exceptions into the right status codes.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.team import Team, TeamMember
from models.user import User

# Ordered low -> high so "does the actor's role outrank what's required"
# is one int comparison instead of a chain of role == "x" or role == "y".
ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}


class TeamNotFoundError(Exception):
    """Team doesn't exist, or the requesting user isn't on it. Deliberately
    the same error either way — a 404 shouldn't reveal that a team you're
    not a member of exists."""

    def __init__(self, team_id: UUID):
        self.team_id = team_id
        super().__init__(f"Team {team_id} not found")


class MemberNotFoundError(Exception):
    def __init__(self, member_id: UUID):
        self.member_id = member_id
        super().__init__(f"Member {member_id} not found")


class PermissionDeniedError(Exception):
    def __init__(self, required_role: str):
        self.required_role = required_role
        super().__init__(f"Requires '{required_role}' role or higher")


def require_role(membership: TeamMember, minimum: str) -> None:
    if ROLE_RANK[membership.role] < ROLE_RANK[minimum]:
        raise PermissionDeniedError(minimum)


# --------------------------------------------------------------- create

async def create_team(db: AsyncSession, *, owner_id: UUID, name: str, logo_url: str | None = None) -> Team:
    team = Team(name=name, logo_url=logo_url, owner_id=owner_id)
    db.add(team)
    await db.flush()  # need team.id before attaching the owner's membership row

    db.add(TeamMember(team_id=team.id, user_id=owner_id, role="owner", status="active"))
    await db.commit()
    await db.refresh(team)
    return team


# ---------------------------------------------------------- read / list

async def list_teams_for_user(db: AsyncSession, *, user_id: UUID) -> list[Team]:
    result = await db.execute(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id, TeamMember.status == "active")
        .order_by(Team.created_at.desc())
    )
    return list(result.scalars().all())


async def get_team_with_membership(db: AsyncSession, *, team_id: UUID, user_id: UUID) -> tuple[Team, TeamMember]:
    """Every team endpoint starts here — confirms the team exists AND that
    the caller belongs to it, in one round trip instead of two."""
    result = await db.execute(
        select(Team, TeamMember)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(Team.id == team_id, TeamMember.user_id == user_id)
    )
    row = result.first()
    if row is None:
        raise TeamNotFoundError(team_id)
    return row.Team, row.TeamMember


# -------------------------------------------------------------- update

async def update_team(db: AsyncSession, *, team: Team, data: dict) -> Team:
    for field, value in data.items():
        setattr(team, field, value)
    await db.commit()
    await db.refresh(team)
    return team


async def delete_team(db: AsyncSession, *, team: Team) -> None:
    await db.delete(team)  # team_members cascades via ON DELETE CASCADE
    await db.commit()


# ------------------------------------------------------------- members

async def list_members(db: AsyncSession, *, team_id: UUID) -> list[tuple[TeamMember, User]]:
    # Join User up front — avoids the classic N+1 (one query for
    # memberships, then a User lookup per row).
    result = await db.execute(
        select(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id)
        .order_by(TeamMember.joined_at)
    )
    return [(row.TeamMember, row.User) for row in result.all()]


async def add_member(db: AsyncSession, *, team_id: UUID, email: str, role: str) -> TeamMember:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        raise ValueError(f"No AGENTX account found for {email}")

    already_on_team = (
        await db.execute(select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user.id))
    ).scalar_one_or_none()
    if already_on_team is not None:
        raise ValueError(f"{email} is already on this team")

    member = TeamMember(team_id=team_id, user_id=user.id, role=role, status="invited")
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def get_member(db: AsyncSession, *, team_id: UUID, member_id: UUID) -> TeamMember:
    result = await db.execute(select(TeamMember).where(TeamMember.id == member_id, TeamMember.team_id == team_id))
    member = result.scalar_one_or_none()
    if member is None:
        raise MemberNotFoundError(member_id)
    return member


async def update_member_role(db: AsyncSession, *, member: TeamMember, new_role: str) -> TeamMember:
    if member.role == "owner":
        # Ownership only moves through transfer_ownership, which updates
        # both memberships atomically — never a bare role edit.
        raise ValueError("Use the transfer-ownership endpoint to change who owns the team")
    member.role = new_role
    await db.commit()
    await db.refresh(member)
    return member


async def remove_member(db: AsyncSession, *, member: TeamMember) -> None:
    if member.role == "owner":
        raise ValueError("Transfer ownership before removing the current owner")
    await db.delete(member)
    await db.commit()


async def transfer_ownership(
    db: AsyncSession, *, team: Team, current_owner: TeamMember, new_owner: TeamMember
) -> None:
    if new_owner.team_id != team.id or current_owner.team_id != team.id:
        raise ValueError("Both memberships must belong to this team")

    current_owner.role = "admin"  # demoted, not removed — keeps full member-management rights
    new_owner.role = "owner"
    team.owner_id = new_owner.user_id
    await db.commit()