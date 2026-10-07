from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.base import utcnow
from database.models import Generation, Payment, User

# Отчёт админу считается по календарю Москвы: платежи ночью не уезжают в прошлый месяц.
_MSK = ZoneInfo("Europe/Moscow")
MONTHS = (
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)


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


def _msk(now_utc_naive: datetime) -> datetime:
    return now_utc_naive.replace(tzinfo=timezone.utc).astimezone(_MSK)


def _to_naive_utc(moment) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def month_start(now_utc_naive: datetime) -> tuple[datetime, str]:
    """Начало текущего календарного месяца по Москве и подпись «Октябрь 2026»."""
    local = _msk(now_utc_naive)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    title = f"{MONTHS[start.month].capitalize()} {start.year}"
    return _to_naive_utc(start), title


def day_start(now_utc_naive: datetime) -> datetime:
    """Полночь текущего дня по Москве, в наивном UTC для сравнения с created_at."""
    local = _msk(now_utc_naive)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return _to_naive_utc(start)


@dataclass
class Stats:
    new_users: int
    generations: dict[str, int]
    cost_usd: float
    stars: int
    tribute_rub: int
    payments: int
    payers: int
    accepted: int


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
    paid = (Payment.created_at >= since, Payment.status == "ok")
    payments = (await session.execute(
        select(func.count()).select_from(Payment).where(*paid)
    )).scalar_one()
    payers = (await session.execute(
        select(func.count(func.distinct(Payment.user_id))).where(*paid)
    )).scalar_one()
    accepted = (await session.execute(
        select(func.count()).select_from(User).where(User.rules_accepted_at >= since)
    )).scalar_one()
    return Stats(
        new_users=int(new_users), generations=gens, cost_usd=cost,
        stars=int(stars), tribute_rub=int(trib) // 100,
        payments=int(payments), payers=int(payers), accepted=int(accepted),
    )


def _day_key(value) -> str:
    """func.date(...) отдаёт date в Postgres и строку 'YYYY-MM-DD' в SQLite."""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


async def daily_series(session: AsyncSession, days: int = 30, now: datetime | None = None) -> list[dict]:
    """Ряд по дням (UTC) за последние `days` суток, включая сегодня.

    Дни без событий тоже присутствуют — графику нужен сплошной ряд.
    """
    now = now or utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=days - 1)
    buckets: dict[str, dict] = {
        _day_key(start + timedelta(days=i)): {
            "date": _day_key(start + timedelta(days=i)),
            "new_users": 0,
            "generations": 0,
            "cost_usd": 0.0,
            "stars": 0,
            "tribute_rub": 0,
        }
        for i in range(days)
    }

    def put(key, field, value):
        row = buckets.get(_day_key(key))
        if row is not None:
            row[field] = value

    users = await session.execute(
        select(func.date(User.created_at), func.count())
        .where(User.created_at >= start)
        .group_by(func.date(User.created_at))
    )
    for day, n in users.all():
        put(day, "new_users", int(n))

    gens = await session.execute(
        select(func.date(Generation.started_at), func.count(), func.coalesce(func.sum(Generation.cost_usd), 0.0))
        .where(Generation.started_at >= start, Generation.status == "done")
        .group_by(func.date(Generation.started_at))
    )
    for day, n, cost in gens.all():
        put(day, "generations", int(n))
        put(day, "cost_usd", round(float(cost or 0), 4))

    stars = await session.execute(
        select(func.date(Payment.created_at), func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.created_at >= start, Payment.provider == "stars", Payment.status == "ok")
        .group_by(func.date(Payment.created_at))
    )
    for day, amount in stars.all():
        put(day, "stars", int(amount))

    trib = await session.execute(
        select(func.date(Payment.created_at), func.coalesce(func.sum(Payment.amount), 0))
        .where(
            Payment.created_at >= start,
            Payment.provider == "tribute",
            Payment.status == "ok",
            func.lower(Payment.currency).in_(["rub", ""]),
        )
        .group_by(func.date(Payment.created_at))
    )
    for day, amount in trib.all():
        put(day, "tribute_rub", int(amount) // 100)

    return [buckets[k] for k in sorted(buckets)]
