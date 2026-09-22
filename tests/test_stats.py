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
        await s.commit()
    async with session_factory() as s:
        st = await stats.collect(s, now - timedelta(days=1))
    assert st.new_users == 1
    assert st.generations == {"base": 1, "premium": 1}
    assert abs(st.cost_usd - 0.052) < 1e-9
    assert st.stars == 250 and st.tribute_rub == 499
