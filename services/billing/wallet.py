from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import CrystalTransaction, User
from database.repo import get_user_for_update


class InsufficientCrystals(Exception):
    def __init__(self, needed: int, balance: int):
        super().__init__(f"need {needed}, have {balance}")
        self.needed = needed
        self.balance = balance


async def get_balance(session: AsyncSession, user_id: int) -> int:
    user = await session.get(User, user_id)
    return user.crystals if user else 0


async def apply(
    session: AsyncSession,
    user_id: int,
    amount: int,
    kind: str,
    ref_type: str | None = None,
    ref_id: str | None = None,
) -> int:
    user = await get_user_for_update(session, user_id)
    if user is None:
        raise ValueError(f"user {user_id} not found")
    new_balance = user.crystals + amount
    if new_balance < 0:
        raise InsufficientCrystals(needed=-amount, balance=user.crystals)
    user.crystals = new_balance
    session.add(
        CrystalTransaction(
            user_id=user_id, kind=kind, amount=amount, balance_after=new_balance,
            ref_type=ref_type, ref_id=ref_id,
        )
    )
    await session.flush()
    return new_balance


async def charge_generation(session: AsyncSession, user_id: int, cost: int, generation_id: int) -> int:
    return await apply(session, user_id, -cost, "charge", "generation", str(generation_id))


async def charge_video(session: AsyncSession, user_id: int, cost: int, ref_id: str) -> int:
    return await apply(session, user_id, -cost, "charge", "video", ref_id)


async def _refund_ref(session: AsyncSession, user_id: int, ref_type: str, ref_id: str) -> int | None:
    if await get_user_for_update(session, user_id) is None:
        return None
    rows = await session.execute(
        select(CrystalTransaction)
        .where(
            CrystalTransaction.user_id == user_id,
            CrystalTransaction.ref_type == ref_type,
            CrystalTransaction.ref_id == ref_id,
        )
        .order_by(CrystalTransaction.id)
    )
    txs = rows.scalars().all()
    charge = next((t for t in txs if t.kind == "charge"), None)
    if charge is None or any(t.kind == "refund" for t in txs):
        return None
    return await apply(session, user_id, -charge.amount, "refund", ref_type, ref_id)


async def refund_generation(session: AsyncSession, user_id: int, generation_id: int) -> int | None:
    # Lock the user row before the idempotency check so concurrent refunds serialize.
    return await _refund_ref(session, user_id, "generation", str(generation_id))


async def refund_video(session: AsyncSession, user_id: int, ref_id: str) -> int | None:
    return await _refund_ref(session, user_id, "video", ref_id)
