# backend/models/log_entry.py
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))

    agent_name: Mapped[str] = mapped_column(String(50), index=True)
    log_level: Mapped[str] = mapped_column(String(20))
    prefix_icon: Mapped[str | None] = mapped_column(String(5))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    agent_color: Mapped[str | None] = mapped_column(String(10))

    severity: Mapped[str] = mapped_column(String(20), default="info", index=True)
    error_code: Mapped[str | None] = mapped_column(String(50))
    stack_trace: Mapped[str | None] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    task: Mapped["Task"] = relationship(back_populates="log_entries")