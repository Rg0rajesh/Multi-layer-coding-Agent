# backend/models/project.py
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    stack_badges: Mapped[list] = mapped_column(JSONB, default=list)  # ["Python", "FastAPI", ...]

    status: Mapped[str] = mapped_column(String(30), default="active")       # active / completed / archived
    visibility: Mapped[str] = mapped_column(String(20), default="private")  # private / team / public
    git_repo_url: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(func.now())
    updated_at: Mapped[datetime] = mapped_column(func.now(), onupdate=func.now())

    owner: Mapped["User"] = relationship(back_populates="projects")
    team: Mapped["Team | None"] = relationship(back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")