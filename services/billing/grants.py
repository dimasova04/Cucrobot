from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment
from database.repo import get_user_for_update
from services.billing import subscriptions, wallet
from services.billing.products import Product, get_product


@dataclass
class GrantResult:
    product: Product
    balance: int
    sub_until: datetime | None


async def payment_exists(session: AsyncSession, provider: str, external_id: str) -> bool:
    res = await session.execute(
        select(Payment.id).where(Payment.provider == provider, Payment.external_id == external_id)
    )
    return res.scalar_one_or_none() is not None


async def grant_product(
    session: AsyncSession,
    provider: str,
    external_id: str,
    user_id: int,
    product_code: str,
    amount: int,
    currency: str,
    raw: dict,
) -> GrantResult | None:
    if await payment_exists(session, provider, external_id):
        return None
    product = get_product(product_code)
    if product is None:
        raise ValueError(f"unknown product {product_code}")
    session.add(
        Payment(
            provider=provider, external_id=external_id, user_id=user_id, product=product_code,
            amount=amount, currency=currency, status="ok", raw=raw,
        )
    )
    await session.flush()
    user = await get_user_for_update(session, user_id)
    sub_until = None
    if product.kind == "pack":
        balance = await wallet.apply(session, user_id, product.crystals, "purchase", "payment", external_id)
    else:
        sub_until = subscriptions.extend(user, product.code, product.days)
        await session.flush()
        balance = user.crystals
    return GrantResult(product=product, balance=balance, sub_until=sub_until)
