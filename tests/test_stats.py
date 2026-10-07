from datetime import datetime, timedelta

from database import repo
from database.base import utcnow
from database.models import Generation, Payment
from services import stats


async def test_collect(session_factory):
    now = utcnow()
    async with session_factory() as s:
        u1 = await repo.get_or_create_user(s, 1, "a")
        u1.rules_accepted_at = now
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
    assert st.payments == 2 and st.payers == 1 and st.accepted == 1


async def test_totals(session_factory):
    now = utcnow()
    async with session_factory() as s:
        u1 = await repo.get_or_create_user(s, 1, "a")
        u1.rules_accepted_at = now
        u1.crystals = 7
        u1.sub_until = now + timedelta(days=3)
        u1.ref_code = "part"
        u2 = await repo.get_or_create_user(s, 2, "b")
        u2.crystals = 5
        u2.sub_until = now - timedelta(days=1)
        s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x", status="done"))
        s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x", status="failed"))
        await s.commit()
    async with session_factory() as s:
        t = await stats.totals(s, now)
    assert (t.users, t.accepted, t.active_subs, t.generations_done, t.crystals_in_wallets) == (2, 1, 1, 1, 12)
    assert t.ref_users == 1


def test_month_start_follows_moscow_calendar():
    # 2026-10-01 00:30 МСК — это ещё 30 сентября по UTC, но уже октябрь для отчёта.
    start, title = stats.month_start(datetime(2026, 9, 30, 21, 30))
    assert start == datetime(2026, 9, 30, 21, 0)
    assert title == "Октябрь 2026"
    start, title = stats.month_start(datetime(2026, 9, 30, 20, 0))
    assert start == datetime(2026, 8, 31, 21, 0)
    assert title == "Сентябрь 2026"
    assert stats.day_start(datetime(2026, 9, 30, 21, 30)) == datetime(2026, 9, 30, 21, 0)


async def test_stats_command_reports_the_current_month(session_factory):
    from bot.handlers.admin.stats import cmd_stats
    from tests.test_bot_core import _AdminMessage

    now = utcnow()
    _, title = stats.month_start(now)
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 1, "a")
        user.rules_accepted_at = now
        s.add(Payment(provider="stars", external_id="c1", user_id=1, product="pack_50", amount=350, currency="XTR"))
        s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x", status="done", cost_usd=0.01))
        await s.commit()
    async with session_factory() as s:
        msg = _AdminMessage()
        await cmd_stats(msg, s)
    text = msg.answers[0]
    assert title in text
    assert "Новые пользователи: 1" in text
    assert "Приняли правила: 1" in text
    assert "Платили: 1 · платежей: 1" in text
    assert "Звёзды: 350" in text
    assert "обычных · 0 премиум" in text


def test_admin_commands_cover_help_list():
    import re
    from bot import texts
    from main import admin_commands

    listed = {c.command for c in admin_commands()}
    for cmd in re.findall(r"/(\w+)", texts.ADM_HELP):
        if cmd not in ("cancel", "unblock"):
            assert cmd in listed, cmd


async def test_daily_series_buckets_days_and_fills_gaps(session_factory):
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    async with session_factory() as s:
        u1 = await repo.get_or_create_user(s, 1, "a")
        u1.created_at = today + timedelta(hours=3)
        u2 = await repo.get_or_create_user(s, 2, "b")
        u2.created_at = today - timedelta(days=2, hours=-1)
        s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x",
                         status="done", cost_usd=0.01, started_at=today + timedelta(hours=1)))
        s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x",
                         status="failed", started_at=today + timedelta(hours=2)))
        s.add(Payment(provider="stars", external_id="c1", user_id=1, product="pack_50",
                      amount=199, currency="XTR", created_at=today + timedelta(hours=4)))
        s.add(Payment(provider="tribute", external_id="t1", user_id=1, product="sub_month",
                      amount=59000, currency="rub", created_at=today + timedelta(hours=5)))
        s.add(Payment(provider="tribute", external_id="unresolved:t9", user_id=1, product="?",
                      amount=99900, currency="rub", status="unresolved", created_at=today + timedelta(hours=6)))
        await s.commit()

    async with session_factory() as s:
        series = await stats.daily_series(s, 7, now)

    assert len(series) == 7
    assert [r["date"] for r in series] == sorted(r["date"] for r in series)
    assert series[-1]["date"] == today.strftime("%Y-%m-%d")
    last = series[-1]
    assert last["new_users"] == 1 and last["generations"] == 1
    assert last["stars"] == 199 and last["tribute_rub"] == 590
    assert abs(last["cost_usd"] - 0.01) < 1e-9
    assert series[-3]["new_users"] == 1
    assert series[-2] == {"date": series[-2]["date"], "new_users": 0, "generations": 0,
                          "cost_usd": 0.0, "stars": 0, "tribute_rub": 0}
