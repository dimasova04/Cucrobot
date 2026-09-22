from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Generation, Payment, User


@dataclass
class Stats:
    new_users: int
    generations: dict[str, int]
    cost_usd: float
    stars: int
    tribute_rub: int


async def collect(session: AsyncSession, since: datetime) -> Stats:
    new_users = (await session.execute(select(func.count()).select_from(User).where(User.created_at >= since))).scalar_one()
    rows = await session.execute(
        select(Generation.model_tier, func.count(), func.coalesce(func.sum(Generation.cost_usd), 0.0))
        .where(Generation.started_at >= since, Generation.status == "done")
        .group_by(Generation.model_tier)
    )
    gens, cost = {}, 0.0
    for tier, n, c in rows.all():
        gens[tier] = n
        cost += float(c or 0)
    # Только проведённые платежи: строки status="unresolved" — это заглушки,
    # по ним ничего не начислено.
    stars = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.created_at >= since, Payment.provider == "stars", Payment.status == "ok"
        )
    )).scalar_one()
    trib = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.created_at >= since, Payment.provider == "tribute", Payment.status == "ok",
            func.lower(Payment.currency).in_(["rub", ""]),
        )
    )).scalar_one()
    return Stats(new_users=int(new_users), generations=gens, cost_usd=cost, stars=int(stars), tribute_rub=int(trib) // 100)
