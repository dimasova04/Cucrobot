from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from database.base import utcnow
from database.models import User
from database.repo import get_user_for_update
from services.billing import subscriptions, wallet


@dataclass
class BonusStatus:
    ready: bool
    amount: int
    wait: timedelta


def bonus_status(user: User, settings: Settings, now: datetime | None = None) -> BonusStatus:
    now = now or utcnow()
    if subscriptions.is_active(user, now):
        amount, hours = settings.bonus_sub_amount, settings.bonus_sub_hours
    else:
        amount, hours = settings.bonus_free_amount, settings.bonus_free_hours
    if user.last_bonus_at is None:
        return BonusStatus(True, amount, timedelta(0))
    ready_at = user.last_bonus_at + timedelta(hours=hours)
    if ready_at <= now:
        return BonusStatus(True, amount, timedelta(0))
    return BonusStatus(False, amount, ready_at - now)


async def claim_bonus(
    session: AsyncSession, user_id: int, settings: Settings, now: datetime | None = None
) -> tuple[int, int] | BonusStatus:
    now = now or utcnow()
    user = await get_user_for_update(session, user_id)
    status = bonus_status(user, settings, now)
    if not status.ready:
        return status
    user.last_bonus_at = now
    balance = await wallet.apply(session, user_id, status.amount, "bonus")
    return status.amount, balance
