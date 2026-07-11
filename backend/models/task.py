# backend/models/task.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(50))
    framework: Mapped[str | None] = mapped_column(String(100))
    project_type: Mapped[str | None] = mapped_column(String(50))
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    coordination_pattern: Mapped[str] = mapped_column(String(30), default="sequential")

    max_exec_minutes: Mapped[int] = mapped_column(Integer, default=10)
    output_format: Mapped[str] = mapped_column(String(30), default="commented")
    git_integration: Mapped[bool] = mapped_column(Boolean, default=False)
    agents_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    context_files: Mapped[list] = mapped_column(JSONB, default=list)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    elapsed_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # workflow-centric metrics (C5)
    replan_count: Mapped[int] = mapped_column(Integer, default=0)
    coder_retries: Mapped[int] = mapped_column(Integer, default=0)
    safety_issues_found: Mapped[int] = mapped_column(Integer, default=0)
    human_interventions: Mapped[int] = mapped_column(Integer, default=0)
    total_lines_written: Mapped[int] = mapped_column(Integer, default=0)
    test_count: Mapped[int] = mapped_column(Integer, default=0)
    tests_passed: Mapped[int] = mapped_column(Integer, default=0)
    review_score: Mapped[float | None] = mapped_column(Numeric(4, 2))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="tasks")
    project: Mapped["Project | None"] = relationship(back_populates="tasks")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    log_entries: Mapped[list["LogEntry"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    code_outputs: Mapped[list["CodeOutput"]] = relationship(back_populates="task", cascade="all, delete-orphan")