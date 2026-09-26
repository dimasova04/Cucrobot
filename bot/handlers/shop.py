from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.handlers.balance import price_label
from services.billing.products import get_product

shop_router = Router(name="shop")


def pay_kb(code: str, settings) -> InlineKeyboardMarkup | None:
    rows = []
    if settings.tribute_url(code):
        rows.append([InlineKeyboardButton(text=texts.BTN_PAY_CARD, url=settings.tribute_url(code))])
    if settings.stars_price(code) > 0:
        rows.append([InlineKeyboardButton(text=texts.BTN_PAY_STARS, callback_data=f"stars:{code}")])
    if settings.tribute_buy_stars_url:
        rows.append([InlineKeyboardButton(text=texts.BTN_BUY_STARS, url=settings.tribute_buy_stars_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


@shop_router.callback_query(F.data.startswith("buy:"))
async def choose_payment(cb: CallbackQuery, settings):
    code = cb.data.split(":")[1]
    product = get_product(code)
    await cb.answer()
    if product is None:
        return
    kb = pay_kb(code, settings)
    if kb is None:
        await cb.message.answer(texts.PRODUCT_NOT_CONFIGURED)
        return
    price = price_label(code, settings)
    if product.kind == "pack":
        text = texts.PAY_CHOOSE_PACK.format(title=product.title, n=product.crystals, price=price)
    else:
        text = texts.PAY_CHOOSE_SUB.format(title=product.title, daily=settings.bonus_sub_amount, price=price, gift=product.crystals)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
