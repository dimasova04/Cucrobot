from datetime import datetime, timedelta

from database.base import utcnow
from database.models import User


def is_active(user: User, now: datetime | None = None) -> bool:
    now = now or utcnow()
    return user.sub_until is not None and user.sub_until > now


def extend(user: User, plan: str, days: int, now: datetime | None = None) -> datetime:
    now = now or utcnow()
    base = user.sub_until if is_active(user, now) else now
    user.sub_until = base + timedelta(days=days)
    user.sub_plan = plan
    return user.sub_until
