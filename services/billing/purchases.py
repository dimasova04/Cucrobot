"""Покупка — строка Payment со статусом ok. Стартовые кристаллики, бонус и /give не считаются."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment


async def has_purchased(session: AsyncSession, user_id: int) -> bool:
    q = select(Payment.id).where(Payment.user_id == user_id, Payment.status == "ok").limit(1)
    return (await session.execute(q)).first() is not None
