from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Generation, Payment, User


@dataclass
class Totals:
    users: int
    accepted: int
    active_subs: int
    generations_done: int
    crystals_in_wallets: int
    ref_users: int


async def totals(session: AsyncSession, now: datetime) -> Totals:
    users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    accepted = (await session.execute(
        select(func.count()).select_from(User).where(User.rules_accepted_at.is_not(None))
    )).scalar_one()
    active_subs = (await session.execute(
        select(func.count()).select_from(User).where(User.sub_until > now)
    )).scalar_one()
    gens = (await session.execute(
        select(func.count()).select_from(Generation).where(Generation.status == "done")
    )).scalar_one()
    crystals = (await session.execute(select(func.coalesce(func.sum(User.crystals), 0)))).scalar_one()
    ref_users = (await session.execute(
        select(func.count()).select_from(User).where(User.ref_code.is_not(None))
    )).scalar_one()
    return Totals(int(users), int(accepted), int(active_subs), int(gens), int(crystals), int(ref_users))


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
