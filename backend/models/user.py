# backend/models/user.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str | None] = mapped_column(String(255))  # null for OAuth-only accounts

    avatar_url: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    website_url: Mapped[str | None] = mapped_column(Text)
    github_url: Mapped[str | None] = mapped_column(Text)
    twitter_handle: Mapped[str | None] = mapped_column(String(50))

    plan: Mapped[str] = mapped_column(String(20), default="free")
    role: Mapped[str] = mapped_column(String(20), default="user")

    github_id: Mapped[str | None] = mapped_column(String(100))
    google_id: Mapped[str | None] = mapped_column(String(100))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    two_fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    two_fa_secret: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    projects: Mapped[list["Project"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")