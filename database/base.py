from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config.settings import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


def _fix_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def make_engine(url: str) -> AsyncEngine:
    url = _fix_url(url)
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool
        return create_async_engine(url, poolclass=StaticPool, connect_args={"check_same_thread": False})
    return create_async_engine(url, pool_size=10, max_overflow=10, pool_pre_ping=True, pool_recycle=1800)


def make_session_factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


_engine: AsyncEngine | None = None
_factory = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = make_engine(get_settings().database_url)
    return _engine


def get_session_factory():
    global _factory
    if _factory is None:
        _factory = make_session_factory(get_engine())
    return _factory


async def init_db() -> None:
    """Схема без Alembic — для тестов и ручных прогонов.
    Боевой старт применяет миграции: database/migrate.py."""
    import database.models  # noqa: F401
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
