import os

import pytest
import pytest_asyncio

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "607396740,470057063")

from database.base import Base, make_engine, make_session_factory  # noqa: E402


@pytest_asyncio.fixture
async def session_factory():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def dispatcher_session_factory():
    """Отдельная БД для тестов на реальном Dispatcher (см. фикстуру `dispatcher`)."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)
    yield factory
    await engine.dispose()


@pytest.fixture(scope="session")
def dispatcher(dispatcher_session_factory):
    """build_dispatcher включает роутеры — модульные синглтоны (actors_router,
    scenes_router, ...), у которых parent_router можно выставить только один
    раз за процесс. Поэтому диспетчер собирается ровно один раз на всю сессию
    тестов и переиспользуется везде, где нужен реальный Dispatcher."""
    from config.settings import Settings
    from main import build_dispatcher

    settings = Settings(_env_file=None, bot_token="x")
    return build_dispatcher(settings, dispatcher_session_factory, generator=None)
