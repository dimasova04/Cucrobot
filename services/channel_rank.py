"""Уровень автора в закрытом канале. Считаются все публикации, даже снятые."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Generation


def level_title(published: int) -> str:
    """0–9 Новичок, 10–49 Завсегдатай, 50–99 Мастер кадра, 100–299 Легенда, от 300 Гуру."""
    if published >= 300:
        return "Гуру"
    if published >= 100:
        return "Легенда"
    if published >= 50:
        return "Мастер кадра"
    if published >= 10:
        return "Завсегдатай"
    return "Новичок"


async def published_count(session: AsyncSession, user_id: int) -> int:
    result = await session.scalar(
        select(func.count())
        .select_from(Generation)
        .where(
            Generation.user_id == user_id,
            Generation.channel_message_id.is_not(None),
        )
    )
    return int(result or 0)
