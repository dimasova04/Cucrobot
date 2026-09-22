from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import keyboards, texts
from services.billing.products import PACKS, SUBS, get_product

shop_router = Router(name="shop")


def shop_kb() -> InlineKeyboardMarkup:
    packs = [(texts.PACK_BTN.format(n=p.crystals), f"buy:{p.code}") for p in PACKS]
    subs = [[(texts.SUB_BTN.format(name=texts.PLAN_NAMES[p.code]), f"buy:{p.code}")] for p in SUBS]
    return keyboards.grid(packs, 3, subs)


def pay_kb(code: str, settings) -> InlineKeyboardMarkup | None:
    rows = []
    if settings.tribute_url(code):
        rows.append([InlineKeyboardButton(text=texts.BTN_PAY_CARD, url=settings.tribute_url(code))])
    if settings.stars_price(code) > 0:
        rows.append([InlineKeyboardButton(text=texts.BTN_PAY_STARS, callback_data=f"stars:{code}")])
    if settings.tribute_buy_stars_url:
        rows.append([InlineKeyboardButton(text=texts.BTN_BUY_STARS, url=settings.tribute_buy_stars_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


@shop_router.message(F.text == texts.BTN_SHOP)
async def open_shop(message: Message):
    await message.answer(texts.SHOP, reply_markup=shop_kb())


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
    await cb.message.answer(texts.PAY_CHOOSE.format(title=product.title), reply_markup=kb)
