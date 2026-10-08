"""Приглашение друга: ссылка inv_<telegram id> и кристаллики пригласившему.

Партнёрские ref_ сюда не кладём: личные ссылки забили бы /refs.
Награда один раз, когда новый человек жмёт «Принимаю».
"""
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import CrystalTransaction, User
from services.billing import wallet

PREFIX = "inv_"


def invite_link(username: str, user_id: int) -> str:
    return f"https://t.me/{username}?start={PREFIX}{user_id}"


def inviter_id_from_payload(payload: str | None) -> int | None:
    if not payload or not payload.startswith(PREFIX):
        return None
    rest = payload[len(PREFIX):]
    if not rest.isdigit() or rest.startswith("0"):
        return None
    return int(rest)


def share_url(link: str, text: str) -> str:
    return "https://t.me/share/url?url=" + quote(link, safe="") + "&text=" + quote(text, safe="")


async def remember_inviter(session: AsyncSession, user: User, inviter_id: int) -> bool:
    """Запоминает пригласившего до принятия правил. Повтор и самоприглашение — мимо."""
    if user.id == inviter_id:
        return False
    if user.rules_accepted_at is not None:
        return False
    if user.invited_by is not None:
        return False
    inviter = await session.get(User, inviter_id)
    if inviter is None or inviter.rules_accepted_at is None:
        return False
    user.invited_by = inviter_id
    return True


async def reward_inviter(session: AsyncSession, friend: User, settings) -> tuple[int, int] | None:
    """+N пригласившему. Повтор по тому же другу не платит."""
    if friend.invited_by is None:
        return None
    amount = int(settings.invite_crystals)
    if amount <= 0:
        return None
    existing = (
        await session.execute(
            select(CrystalTransaction.id).where(
                CrystalTransaction.kind == "invite",
                CrystalTransaction.ref_type == "user",
                CrystalTransaction.ref_id == str(friend.id),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None
    if await session.get(User, friend.invited_by) is None:
        return None
    balance = await wallet.apply(session, friend.invited_by, amount, "invite", "user", str(friend.id))
    return amount, balance
