import pytest
import pytest_asyncio

from database import repo
from database.base import Base, make_engine, make_session_factory
from services.billing import wallet


@pytest_asyncio.fixture
async def two_factories(tmp_path):
    """Две независимые сессии-фабрики на ОДИН файл SQLite: каждая со своим
    подключением, как два воркера на одной базе."""
    url = f"sqlite+aiosqlite:///{tmp_path}/t.db"
    engine_a, engine_b = make_engine(url), make_engine(url)
    async with engine_a.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield make_session_factory(engine_a), make_session_factory(engine_b)
    await engine_a.dispose()
    await engine_b.dispose()


async def _user(factory, uid=1, crystals=0):
    async with factory() as s:
        u = await repo.get_or_create_user(s, uid, "u")
        u.crystals = crystals
        await s.commit()


async def test_apply_credit_and_debit(session_factory):
    await _user(session_factory, 1, 0)
    async with session_factory() as s:
        assert await wallet.apply(s, 1, 3, "start") == 3
        assert await wallet.apply(s, 1, -1, "charge", "generation", "10") == 2
        await s.commit()
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 2


async def test_debit_below_zero_raises_and_writes_nothing(session_factory):
    await _user(session_factory, 1, 1)
    async with session_factory() as s:
        with pytest.raises(wallet.InsufficientCrystals) as e:
            await wallet.apply(s, 1, -3, "charge", "generation", "11")
        assert (e.value.needed, e.value.balance) == (3, 1)
        await s.commit()
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 1


async def test_refund_is_idempotent(session_factory):
    await _user(session_factory, 1, 5)
    async with session_factory() as s:
        await wallet.charge_generation(s, 1, 3, 77)
        await s.commit()
    async with session_factory() as s:
        assert await wallet.refund_generation(s, 1, 77) == 5
        await s.commit()
    async with session_factory() as s:
        assert await wallet.refund_generation(s, 1, 77) is None
        await s.commit()
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 5


async def test_refund_without_charge_is_noop(session_factory):
    await _user(session_factory, 1, 5)
    async with session_factory() as s:
        assert await wallet.refund_generation(s, 1, 999) is None


async def test_for_update_refreshes_stale_identity_map(two_factories):
    fa, fb = two_factories
    await _user(fa, 1, 10)
    async with fa() as sa:
        stale = await repo.get_user(sa, 1)
        assert stale.crystals == 10
        # другой процесс меняет баланс и коммитит
        async with fb() as sb:
            other = await repo.get_user_for_update(sb, 1)
            other.crystals = 99
            await sb.commit()
        fresh = await repo.get_user_for_update(sa, 1)
        assert fresh.crystals == 99
        assert stale.crystals == 99  # тот же объект identity map, но перечитанный


async def test_concurrent_applies_do_not_lose_update(two_factories):
    fa, fb = two_factories
    await _user(fa, 1, 10)
    async with fa() as sa:
        stale = await repo.get_user(sa, 1)  # сессия A держит устаревший объект
        assert stale.crystals == 10
        async with fb() as sb:
            assert await wallet.apply(sb, 1, 5, "admin") == 15
            await sb.commit()
        assert await wallet.apply(sa, 1, -3, "charge", "generation", "1") == 12
        await sa.commit()
    async with fa() as sa:
        assert await wallet.get_balance(sa, 1) == 12
