"""10 👎 снимают пост. Три таких предупреждения за 7 дней закрывают канал на 30 дней."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ChannelWarning, Generation, User

DOWNVOTE = "👎"
DOWNVOTES_TO_REMOVE = 10
WARNINGS_FOR_BAN = 3
WARNING_WINDOW = timedelta(days=7)
BAN_FOR = timedelta(days=30)
_MSK = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class Strike:
    user_id: int
    warnings: int
    ban_until: datetime | None


def downvote_total(reactions) -> int:
    """Сколько 👎 сейчас стоит на посте. Лайки, огонь и платные не считаются."""
    total = 0
    for item in reactions:
        kind = getattr(item, "type", None)
        if getattr(kind, "emoji", None) != DOWNVOTE:
            continue
        total += int(item.total_count)
    return total


def posting_banned(user, now: datetime) -> bool:
    until = getattr(user, "channel_ban_until", None)
    return until is not None and until > now


def format_ban_until(moment: datetime) -> str:
    aware = moment.replace(tzinfo=timezone.utc).astimezone(_MSK)
    return aware.strftime("%d.%m.%Y %H:%M")


async def record_strike(session: AsyncSession, gen: Generation, now: datetime) -> Strike | None:
    """Одно предупреждение на пост. None, если этот кадр уже снимали."""
    if gen.channel_removed_at is not None:
        return None
    already = await session.scalar(
        select(ChannelWarning.id).where(ChannelWarning.generation_id == gen.id)
    )
    if already is not None:
        gen.channel_removed_at = now
        return None
    gen.channel_removed_at = now
    session.add(ChannelWarning(user_id=gen.user_id, generation_id=gen.id, created_at=now))
    await session.flush()
    since = now - WARNING_WINDOW
    warnings = await session.scalar(
        select(func.count())
        .select_from(ChannelWarning)
        .where(
            ChannelWarning.user_id == gen.user_id,
            ChannelWarning.created_at >= since,
        )
    )
    warnings = int(warnings or 0)
    user = await session.get(User, gen.user_id)
    ban_until = None
    if warnings >= WARNINGS_FOR_BAN and user is not None:
        until = now + BAN_FOR
        if user.channel_ban_until is None or user.channel_ban_until < until:
            user.channel_ban_until = until
        ban_until = user.channel_ban_until
    return Strike(user_id=gen.user_id, warnings=warnings, ban_until=ban_until)
