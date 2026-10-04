"""Реф-ссылки для партнёров: коды, привязка пользователей и статистика по ним.

Выплаты делаются вручную вне бота — здесь только учёт.
"""
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.base import utcnow
from database.models import Generation, Payment, ReferralCode, User

CODE_RE = re.compile(r"^[a-z0-9_]{3,32}$")
DEEP_LINK_PREFIX = "ref_"
# Кнопка «Создать своё» под постом канала. В /refs этот код виден отдельно.
CHANNEL_CODE = "channel"


def normalize_code(raw: str) -> str | None:
    code = (raw or "").strip().lower()
    return code if CODE_RE.fullmatch(code) else None


def link_for(bot_username: str, code: str) -> str:
    payload = code if code == CHANNEL_CODE else f"{DEEP_LINK_PREFIX}{code}"
    return f"https://t.me/{bot_username}?start={payload}"


def code_from_payload(payload: str | None) -> str | None:
    """Код из пейлоада `/start ref_xxx` или `/start channel`."""
    if payload == CHANNEL_CODE:
        return CHANNEL_CODE
    if not payload or not payload.startswith(DEEP_LINK_PREFIX):
        return None
    return normalize_code(payload[len(DEEP_LINK_PREFIX):])


async def ensure_code(session: AsyncSession, code: str, title: str) -> ReferralCode:
    """Код для учёта. Повторный запуск при старте бота его не затирает."""
    normalized = normalize_code(code)
    if normalized is None:
        raise ValueError(f"invalid referral code {code!r}")
    existing = await get_code(session, normalized)
    if existing is not None:
        return existing
    return await create_code(session, normalized, title, None, None)


async def get_code(session: AsyncSession, code: str) -> ReferralCode | None:
    return await session.get(ReferralCode, code)


async def create_code(
    session: AsyncSession, code: str, title: str, partner_user_id: int | None, created_by: int | None
) -> ReferralCode:
    normalized = normalize_code(code)
    if normalized is None:
        raise ValueError(f"invalid referral code {code!r}")
    if await get_code(session, normalized) is not None:
        raise ValueError(f"referral code {normalized!r} already exists")
    rc = ReferralCode(
        code=normalized,
        title=title.strip()[:64],
        partner_user_id=partner_user_id,
        created_by=created_by,
    )
    session.add(rc)
    await session.flush()
    return rc


async def list_codes(session: AsyncSession) -> list[ReferralCode]:
    q = select(ReferralCode).order_by(ReferralCode.created_at, ReferralCode.code)
    return list((await session.execute(q)).scalars().all())


async def codes_for_partner(session: AsyncSession, partner_user_id: int) -> list[ReferralCode]:
    q = (
        select(ReferralCode)
        .where(ReferralCode.partner_user_id == partner_user_id)
        .order_by(ReferralCode.created_at, ReferralCode.code)
    )
    return list((await session.execute(q)).scalars().all())


async def set_active(session: AsyncSession, code: str, active: bool) -> ReferralCode | None:
    rc = await get_code(session, code)
    if rc is None:
        return None
    rc.is_active = active
    await session.flush()
    return rc


async def attribute(session: AsyncSession, user: User, code: str) -> bool:
    """Привязать пользователя к коду. Привязка делается один раз и навсегда."""
    if user.ref_code is not None:
        return False
    rc = await get_code(session, code)
    if rc is None or not rc.is_active:
        return False
    user.ref_code = rc.code
    user.ref_attributed_at = utcnow()
    await session.flush()
    return True


@dataclass
class RefStats:
    code: str
    title: str
    users: int
    accepted: int
    paying_users: int
    stars: int
    tribute_rub: int
    generations_done: int


async def stats_for(session: AsyncSession, code: str, since: datetime | None = None) -> RefStats:
    rc = await get_code(session, code)
    title = rc.title if rc is not None else ""

    referred = select(User.id).where(User.ref_code == code)
    window = referred if since is None else referred.where(User.ref_attributed_at >= since)

    users = (await session.execute(
        select(func.count()).select_from(User).where(User.id.in_(window))
    )).scalar_one()
    accepted = (await session.execute(
        select(func.count()).select_from(User).where(
            User.id.in_(window), User.rules_accepted_at.is_not(None)
        )
    )).scalar_one()

    # Доход считаем только по проведённым платежам: status="unresolved" — заглушки.
    paid = [Payment.user_id.in_(referred), Payment.status == "ok"]
    if since is not None:
        paid.append(Payment.created_at >= since)
    paying_users = (await session.execute(
        select(func.count(func.distinct(Payment.user_id))).where(*paid)
    )).scalar_one()
    stars = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(*paid, Payment.provider == "stars")
    )).scalar_one()
    tribute = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            *paid, Payment.provider == "tribute", func.lower(Payment.currency).in_(["rub", ""])
        )
    )).scalar_one()

    gens_where = [Generation.user_id.in_(referred), Generation.status == "done"]
    if since is not None:
        gens_where.append(Generation.started_at >= since)
    gens = (await session.execute(
        select(func.count()).select_from(Generation).where(*gens_where)
    )).scalar_one()

    return RefStats(
        code=code,
        title=title,
        users=int(users),
        accepted=int(accepted),
        paying_users=int(paying_users),
        stars=int(stars),
        tribute_rub=int(tribute) // 100,
        generations_done=int(gens),
    )


async def stats_all(session: AsyncSession, since: datetime | None = None) -> list[RefStats]:
    return [await stats_for(session, rc.code, since) for rc in await list_codes(session)]
