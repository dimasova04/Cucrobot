"""Имя для закрытого канала. Одно на пользователя, без телеграм-ника."""
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User

# Короткие английские прозвища. Повтор не выдаём, пока в списке есть свободные.
NAMES = (
    "Lord M", "Tsar", "Duke", "Baron", "Captain", "Don", "King", "Count",
    "Sir", "Knight", "Prince", "Sultan", "Khan", "Pharaoh", "Viking",
    "Sheriff", "Major", "Admiral", "Maestro", "Cowboy", "Chief", "Boss",
    "Emperor", "Marquis", "Earl", "Commodore", "Ranger", "Ace", "Joker",
    "Ghost", "Hawk", "Fox", "Lion", "Wolf", "Storm", "Blaze", "Lucky",
    "Mister", "Rocket", "Rider", "Hunter", "Pilot", "Doc", "Professor",
    "Lord K", "Duke V", "Baron M", "Don K", "King J", "Count R",
    "Captain Z", "Tsar N", "Khan B", "Major T", "Admiral Q", "Sheriff J",
    "Maestro V", "Chief W", "Earl P", "Ranger S", "Ghost X", "Hawk F",
)


async def assign_public_name(session: AsyncSession, user: User) -> str:
    """Первая публикация выдаёт имя. Дальше оно то же самое."""
    if user.public_name:
        return user.public_name
    taken = set((await session.scalars(select(User.public_name).where(User.public_name.is_not(None)))).all())
    free = [name for name in NAMES if name not in taken]
    for _ in range(8):
        if free:
            name = secrets.choice(free)
            free.remove(name)
        else:
            name = f"{secrets.choice(NAMES)} {secrets.randbelow(900) + 100}"
            if name in taken:
                continue
        user.public_name = name
        try:
            async with session.begin_nested():
                await session.flush()
        except IntegrityError:
            user.public_name = None
            taken.add(name)
            continue
        return name
    raise RuntimeError("could not assign a public name")
