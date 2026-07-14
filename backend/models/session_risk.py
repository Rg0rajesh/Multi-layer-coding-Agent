# backend/models/session_risk.py
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class SessionRiskScore(Base):
    """
    Tracks Guardrail's running risk assessment for a task's session.
    One row per task — Guardrail reads this before scoring a new message
    and writes back after, per the 0.6/0.4 decay formula in the master prompt.
    """
    __tablename__ = "session_risk_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), unique=True, index=True
    )

    running_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    last_verdict: Mapped[str] = mapped_column(String(20), default="allow")  # allow / flag / block

    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    task: Mapped["Task"] = relationship(back_populates="risk_score")