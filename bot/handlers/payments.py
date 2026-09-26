from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery
from loguru import logger

from bot import texts
from services.billing import grants
from services.payments import stars

payments_router = Router(name="payments")


@payments_router.callback_query(F.data.startswith("stars:"))
async def send_stars_invoice(cb: CallbackQuery, bot: Bot, settings):
    code = cb.data.split(":")[1]
    await cb.answer()
    try:
        params = stars.invoice_params(code, settings)
    except ValueError:
        await cb.message.answer(texts.PRODUCT_NOT_CONFIGURED)
        return
    await bot.send_invoice(chat_id=cb.from_user.id, **params)


@payments_router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@payments_router.message(F.successful_payment)
async def on_successful_payment(message: Message, session, user):
    sp = message.successful_payment
    code = stars.parse_payload(sp.invoice_payload)
    if code is None:
        logger.error("stars payment with unknown payload {}", sp.invoice_payload)
        return
    res = await grants.grant_product(
        session, "stars", sp.telegram_payment_charge_id, user.id, code, sp.total_amount, "XTR",
        raw=sp.model_dump(mode="json"),
    )
    if res is None:
        logger.warning("duplicate stars payment {}", sp.telegram_payment_charge_id)
        return
    # Деньги уже списаны Telegram: фиксируем начисление до отправки сообщения,
    # чтобы упавший answer() не откатил транзакцию в DbSessionMiddleware.
    await session.commit()
    text = (
        texts.PAYMENT_OK_PACK.format(n=res.product.crystals, balance=res.balance)
        if res.product.kind == "pack"
        else texts.PAYMENT_OK_SUB.format(until=res.sub_until.strftime("%d.%m.%Y"), n=res.product.crystals, balance=res.balance)
    )
    try:
        await message.answer(text)
    except Exception as e:
        logger.warning("stars payment {} granted, but confirmation failed: {}", sp.telegram_payment_charge_id, e)
