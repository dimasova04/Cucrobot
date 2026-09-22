import asyncio

import pytest

from database import repo
from services.billing import wallet


async def _user(factory, uid=1, crystals=0):
    async with factory() as s:
        u = await repo.get_or_create_user(s, uid, "u")
        u.crystals = crystals
        await s.commit()


async def test_apply_credit_and_debit(session_factory):
    await _user(session_factory, 1, 0)
    async with session_factory() as s:
        assert await wallet.apply(s, 1, 3, "start") == 3
        assert await wallet.apply(s, 1, -1, "charge", "generation", "10") == 2
        await s.commit()
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 2


async def test_debit_below_zero_raises_and_writes_nothing(session_factory):
    await _user(session_factory, 1, 1)
    async with session_factory() as s:
        with pytest.raises(wallet.InsufficientCrystals) as e:
            await wallet.apply(s, 1, -3, "charge", "generation", "11")
        assert (e.value.needed, e.value.balance) == (3, 1)
        await s.commit()
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 1


async def test_refund_is_idempotent(session_factory):
    await _user(session_factory, 1, 5)
    async with session_factory() as s:
        await wallet.charge_generation(s, 1, 3, 77)
        await s.commit()
    async with session_factory() as s:
        assert await wallet.refund_generation(s, 1, 77) == 5
        await s.commit()
    async with session_factory() as s:
        assert await wallet.refund_generation(s, 1, 77) is None
        await s.commit()
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 5


async def test_refund_without_charge_is_noop(session_factory):
    await _user(session_factory, 1, 5)
    async with session_factory() as s:
        assert await wallet.refund_generation(s, 1, 999) is None
