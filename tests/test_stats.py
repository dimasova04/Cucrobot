from datetime import timedelta

from database import repo
from database.base import utcnow
from database.models import Generation, Payment
from services import stats


async def test_collect(session_factory):
    now = utcnow()
    async with session_factory() as s:
        await repo.get_or_create_user(s, 1, "a")
        u2 = await repo.get_or_create_user(s, 2, "b")
        u2.created_at = now - timedelta(days=10)
        s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x", status="done", cost_usd=0.002))
        s.add(Generation(user_id=1, model_air="m", model_tier="premium", actors=[], location="x", status="done", cost_usd=0.05))
        s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x", status="failed"))
        s.add(Payment(provider="stars", external_id="c1", user_id=1, product="pack_50", amount=250, currency="XTR"))
        s.add(Payment(provider="tribute", external_id="t1", user_id=1, product="sub_month", amount=49900, currency="rub"))
        # заглушки неразобранных платежей в доход не попадают
        s.add(Payment(provider="tribute", external_id="unresolved:t9", user_id=1, product="?", amount=99900, currency="rub", status="unresolved"))
        s.add(Payment(provider="stars", external_id="unresolved:c9", user_id=1, product="?", amount=9999, currency="XTR", status="unresolved"))
        await s.commit()
    async with session_factory() as s:
        st = await stats.collect(s, now - timedelta(days=1))
    assert st.new_users == 1
    assert st.generations == {"base": 1, "premium": 1}
    assert abs(st.cost_usd - 0.052) < 1e-9
    assert st.stars == 250 and st.tribute_rub == 499


async def test_totals(session_factory):
    now = utcnow()
    async with session_factory() as s:
        u1 = await repo.get_or_create_user(s, 1, "a")
        u1.rules_accepted_at = now
        u1.crystals = 7
        u1.sub_until = now + timedelta(days=3)
        u2 = await repo.get_or_create_user(s, 2, "b")
        u2.crystals = 5
        u2.sub_until = now - timedelta(days=1)
        s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x", status="done"))
        s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x", status="failed"))
        await s.commit()
    async with session_factory() as s:
        t = await stats.totals(s, now)
    assert (t.users, t.accepted, t.active_subs, t.generations_done, t.crystals_in_wallets) == (2, 1, 1, 1, 12)


def test_admin_commands_cover_help_list():
    import re
    from bot import texts
    from main import admin_commands

    listed = {c.command for c in admin_commands()}
    for cmd in re.findall(r"/(\w+)", texts.ADM_HELP):
        if cmd not in ("cancel", "unblock"):
            assert cmd in listed, cmd
