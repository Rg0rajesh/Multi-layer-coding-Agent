# backend/database.py
from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

# Consistent constraint naming so Alembic autogenerate doesn't spit out
# things like "ck_tasks_a1b2c3" that mean nothing six months from now.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _async_database_url(raw_url: str) -> str:
    """
    DATABASE_URL in .env is the plain postgresql:// form people write by
    hand (and what alembic/psql expect) — asyncpg needs the +asyncpg
    driver suffix. A blind string .replace("postgresql://", ...) breaks
    the moment DATABASE_URL is anything other than that exact bare scheme
    (e.g. postgresql+psycopg2://...). Parsing it with SQLAlchemy's own
    URL type means only the driver gets touched, never the rest of the URL.
    """
    url = make_url(raw_url)
    if url.get_backend_name() == "postgresql" and url.get_driver_name() in ("psycopg2", ""):
        url = url.set(drivername="postgresql+asyncpg")
    return str(url)


engine = create_async_engine(
    _async_database_url(settings.database_url),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, always closes it."""
    async with async_session_factory() as session:
        yield session