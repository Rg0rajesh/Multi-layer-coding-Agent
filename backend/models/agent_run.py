
# backend/models/agent_run.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)

    agent_name: Mapped[str] = mapped_column(String(50), index=True)  # PLANNER / CODER / TESTER / ...
    agent_color: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(30), default="pending")

    current_subtask: Mapped[str | None] = mapped_column(Text)
    step_current: Mapped[int] = mapped_column(Integer, default=0)
    step_total: Mapped[int] = mapped_column(Integer, default=0)

    # Shape varies per agent — Planner tracks subtasks_created, Coder tracks
    # lines_written, etc. Kept schemaless on purpose; validated in the service layer.
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    input_data: Mapped[dict | None] = mapped_column(JSONB)
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    task: Mapped["Task"] = relationship(back_populates="agent_runs")