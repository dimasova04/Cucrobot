from datetime import datetime, timedelta

from config.settings import Settings
from database import repo
from database.models import User
from services.billing import bonus, grants, products, subscriptions


def _settings():
    return Settings(_env_file=None, bot_token="x")


def test_products_catalog():
    assert [p.code for p in products.PACKS] == ["pack_50", "pack_100", "pack_300"]
    assert [p.crystals for p in products.PACKS] == [50, 100, 300]
    assert [p.days for p in products.SUBS] == [7, 30, 90]
    assert [p.crystals for p in products.SUBS] == [5, 20, 60]
    assert products.get_product("nope") is None


def test_subscription_extend_from_now_when_expired():
    now = datetime(2026, 1, 1)
    u = User(id=1, sub_until=now - timedelta(days=5))
    until = subscriptions.extend(u, "sub_week", 7, now=now)
    assert until == now + timedelta(days=7)
    assert u.sub_plan == "sub_week"
    assert subscriptions.is_active(u, now)


def test_subscription_extend_stacks_when_active():
    now = datetime(2026, 1, 1)
    u = User(id=1, sub_plan="sub_week", sub_until=now + timedelta(days=2))
    until = subscriptions.extend(u, "sub_month", 30, now=now)
    assert until == now + timedelta(days=32)


def test_bonus_status_free_and_sub():
    s = _settings()
    now = datetime(2026, 1, 10, 12)
    free = User(id=1, last_bonus_at=now - timedelta(hours=23))
    st = bonus.bonus_status(free, s, now)
    assert not st.ready and st.amount == 3 and st.wait == timedelta(hours=1)
    sub = User(id=2, sub_plan="sub_week", sub_until=now + timedelta(days=1), last_bonus_at=now - timedelta(hours=25))
    st = bonus.bonus_status(sub, s, now)
    assert st.ready and st.amount == 10
    never = User(id=3)
    assert bonus.bonus_status(never, s, now).ready


async def test_claim_bonus_grants_once(session_factory):
    s = _settings()
    now = datetime(2026, 1, 10, 12)
    async with session_factory() as db:
        await repo.get_or_create_user(db, 1, "u")
        await db.commit()
    async with session_factory() as db:
        assert await bonus.claim_bonus(db, 1, s, now) == (3, 3)
        await db.commit()
    async with session_factory() as db:
        res = await bonus.claim_bonus(db, 1, s, now + timedelta(hours=1))
        assert isinstance(res, bonus.BonusStatus) and res.wait == timedelta(hours=23)


async def test_grant_product_pack_and_sub_idempotent(session_factory):
    async with session_factory() as db:
        await repo.get_or_create_user(db, 1, "u")
        await db.commit()
    async with session_factory() as db:
        r = await grants.grant_product(db, "stars", "ch_1", 1, "pack_50", 250, "XTR", {})
        assert r.balance == 50 and r.sub_until is None
        await db.commit()
    async with session_factory() as db:
        assert await grants.grant_product(db, "stars", "ch_1", 1, "pack_50", 250, "XTR", {}) is None
        r = await grants.grant_product(db, "tribute", "p_9", 1, "sub_month", 49900, "RUB", {"x": 1})
        assert r.sub_until is not None and r.balance == 70  # 50 за пакет + 20 подарок за месяц
        await db.commit()
    async with session_factory() as db:
        u = await repo.get_user(db, 1)
        assert u.sub_plan == "sub_month" and u.crystals == 70


async def test_grant_product_concurrent_duplicate_returns_none(session_factory, monkeypatch):
    async def never_exists(session, provider, external_id):
        return False
    monkeypatch.setattr(grants, "payment_exists", never_exists)
    async with session_factory() as db:
        await repo.get_or_create_user(db, 1, "u")
        await db.commit()
    async with session_factory() as db:
        assert (await grants.grant_product(db, "stars", "dup", 1, "pack_50", 250, "XTR", {})).balance == 50
        await db.commit()
    async with session_factory() as db:
        assert await grants.grant_product(db, "stars", "dup", 1, "pack_50", 250, "XTR", {}) is None
        await db.commit()
    async with session_factory() as db:
        assert (await repo.get_user(db, 1)).crystals == 50
