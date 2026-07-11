
# backend/models/code_output.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class CodeOutput(Base):
    __tablename__ = "code_outputs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))

    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(50))
    line_count: Mapped[int] = mapped_column(Integer, default=0)

    is_new_file: Mapped[bool] = mapped_column(Boolean, default=True)
    is_test_file: Mapped[bool] = mapped_column(Boolean, default=False)
    is_doc_file: Mapped[bool] = mapped_column(Boolean, default=False)

    annotations: Mapped[list] = mapped_column(JSONB, default=list)  # [{line, agent, note, color}]

    created_at: Mapped[datetime] = mapped_column(func.now())
    updated_at: Mapped[datetime] = mapped_column(func.now(), onupdate=func.now())

    task: Mapped["Task"] = relationship(back_populates="code_outputs")