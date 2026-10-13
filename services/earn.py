"""Партнёрка «Зарабатывай»: процент с оплат приглашённых и заявки на вывод.

Ссылка — личная inv_. Кристаллики за приглашение считаются отдельно.
"""
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.base import utcnow
from database.models import Payment, ReferralPayout, User

# USDT TRC20: T + 33 символа base58. TON: EQ/UQ/kQ и 46 символов.
_TRC20 = re.compile(r"T[1-9A-HJ-NP-Za-km-z]{33}")
_TON = re.compile(r"(?:EQ|UQ|kQ)[A-Za-z0-9_-]{46}")
_USERNAME = re.compile(r"[A-Za-z0-9_]{5,32}")


@dataclass(frozen=True)
class EarnStats:
    registrations: int
    payments: int
    accrued_kop: int
    paid_kop: int
    pending_kop: int

    @property
    def available_kop(self) -> int:
        return max(0, self.accrued_kop - self.paid_kop - self.pending_kop)


def rub(kop: int) -> str:
    kop = max(0, int(kop))
    return f"{kop // 100}.{kop % 100:02d} ₽"


def parse_payout_text(text: str) -> tuple[str, str] | None:
    """Две строки или «юзернейм кошелёк». Юзернейм Telegram и USDT TON или TRC20."""
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return None
    lines = [part.strip() for part in raw.splitlines() if part.strip()]
    if len(lines) == 1:
        bits = lines[0].split()
        if len(bits) < 2:
            return None
        lines = [bits[0], bits[1]]
    username = lines[0].lstrip("@")
    wallet = lines[1].strip()
    if _USERNAME.fullmatch(username) is None:
        return None
    if _TRC20.fullmatch(wallet) is None and _TON.fullmatch(wallet) is None:
        return None
    return username, wallet


async def stats_for(session: AsyncSession, user_id: int, rate_percent: int) -> EarnStats:
    referred = select(User.id).where(
        User.invited_by == user_id,
        User.rules_accepted_at.is_not(None),
    )
    registrations = (
        await session.execute(select(func.count()).select_from(User).where(User.id.in_(referred)))
    ).scalar_one()
    paid = [
        Payment.user_id.in_(referred),
        Payment.status == "ok",
        Payment.provider == "tribute",
        func.lower(Payment.currency).in_(["rub", ""]),
    ]
    payments = (
        await session.execute(select(func.count()).select_from(Payment).where(*paid))
    ).scalar_one()
    gross = (
        await session.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(*paid))
    ).scalar_one()
    accrued = int(gross) * int(rate_percent) // 100
    paid_kop = (
        await session.execute(
            select(func.coalesce(func.sum(ReferralPayout.amount_kop), 0)).where(
                ReferralPayout.user_id == user_id,
                ReferralPayout.status == "paid",
            )
        )
    ).scalar_one()
    pending_kop = (
        await session.execute(
            select(func.coalesce(func.sum(ReferralPayout.amount_kop), 0)).where(
                ReferralPayout.user_id == user_id,
                ReferralPayout.status == "pending",
            )
        )
    ).scalar_one()
    return EarnStats(
        registrations=int(registrations),
        payments=int(payments),
        accrued_kop=accrued,
        paid_kop=int(paid_kop),
        pending_kop=int(pending_kop),
    )


async def pending_payout(session: AsyncSession, user_id: int) -> ReferralPayout | None:
    q = (
        select(ReferralPayout)
        .where(ReferralPayout.user_id == user_id, ReferralPayout.status == "pending")
        .order_by(ReferralPayout.id.desc())
    )
    return (await session.execute(q)).scalars().first()


async def create_payout(
    session: AsyncSession,
    user_id: int,
    tg_username: str,
    wallet: str,
    *,
    rate_percent: int,
    min_rub: int,
) -> ReferralPayout | str:
    """pending — заявка уже есть. low — баланс меньше минимума. Иначе новая заявка на весь доступный баланс."""
    if await pending_payout(session, user_id) is not None:
        return "pending"
    cabinet = await stats_for(session, user_id, rate_percent)
    if cabinet.available_kop < int(min_rub) * 100:
        return "low"
    row = ReferralPayout(
        user_id=user_id,
        amount_kop=cabinet.available_kop,
        tg_username=tg_username,
        wallet=wallet,
        status="pending",
    )
    session.add(row)
    await session.flush()
    return row


async def mark_paid(session: AsyncSession, payout_id: int) -> ReferralPayout | None:
    """Списывает заявку. Повтор ничего не меняет и возвращает None."""
    row = await session.get(ReferralPayout, payout_id)
    if row is None or row.status != "pending":
        return None
    row.status = "paid"
    row.paid_at = utcnow()
    await session.flush()
    return row
