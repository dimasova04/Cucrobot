from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from services.billing.products import get_product

shop_router = Router(name="shop")


def pay_kb(code: str, settings) -> InlineKeyboardMarkup | None:
    rows = []
    if settings.tribute_url(code):
        rub = settings.rub_price(code)
        label = texts.BTN_PAY_CARD.format(price=f" — {rub} ₽" if rub > 0 else "")
        rows.append([InlineKeyboardButton(text=label, url=settings.tribute_url(code))])
    if settings.stars_price(code) > 0:
        label = texts.BTN_PAY_STARS.format(stars=settings.stars_price(code))
        rows.append([InlineKeyboardButton(text=label, callback_data=f"stars:{code}")])
    if settings.tribute_buy_stars_url:
        rows.append([InlineKeyboardButton(text=texts.BTN_BUY_STARS, url=settings.tribute_buy_stars_url)])
    if not rows:
        return None
    rows.append([InlineKeyboardButton(text=texts.BTN_BACK, callback_data="menu:profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    if product.kind == "pack":
        text = texts.PAY_CHOOSE_PACK.format(title=product.title, n=product.crystals)
    else:
        text = texts.PAY_CHOOSE_SUB.format(title=product.title, daily=settings.bonus_sub_amount, gift=product.crystals)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
