# backend/models/identity_token.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class IdentityToken(Base):
    """
    Scoped, short-lived credential issued by the Identity Broker before
    Coder/Tester run any tool call. tool_call_log is append-only — the
    broker adds an entry every time a tool call is made under this token,
    so it doubles as an audit trail.
    """
    __tablename__ = "identity_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)

    scope: Mapped[dict] = mapped_column(JSONB, default=dict)
    tool_call_log: Mapped[list] = mapped_column(JSONB, default=list)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    task: Mapped["Task"] = relationship(back_populates="identity_tokens")