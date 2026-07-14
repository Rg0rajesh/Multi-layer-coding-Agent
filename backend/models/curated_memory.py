# backend/models/curated_memory.py
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class CuratedMemory(Base):
    """
    Output of the Context Curator (C6). Raw session logs never get promoted
    into ChromaDB Tier 2 directly — the Curator tags each notable event first,
    and only architectural_decision / known_bug items land here. This table
    is the source of truth; the ChromaDB embedding is a derived index over it.
    """
    __tablename__ = "curated_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL")
    )  # deliberately not CASCADE — memory should outlive the task that created it

    tag: Mapped[str] = mapped_column(String(30), index=True)  # architectural_decision / known_bug
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="curated_memory")