from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.get(User, telegram_id)


async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str | None) -> User:
    user = await session.get(User, telegram_id)
    if user is None:
        user = User(id=telegram_id, username=username)
        session.add(user)
        await session.flush()
    elif username and user.username != username:
        user.username = username
    return user


async def get_user_for_update(session: AsyncSession, telegram_id: int) -> User | None:
    # populate_existing: без него SELECT ... FOR UPDATE вернул бы устаревший объект из
    # identity map сессии, и блокировка строки не защитила бы от потерянного обновления.
    res = await session.execute(
        select(User)
        .where(User.id == telegram_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return res.scalar_one_or_none()
