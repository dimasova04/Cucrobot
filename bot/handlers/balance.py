from datetime import timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from loguru import logger

from bot import keyboards, texts
from bot.bonus_card import send_bonus_card
from services.billing import bonus, subscriptions
from services.billing.products import PACKS, SUBS

profile_router = Router(name="profile")


def _fmt_wait(wait: timedelta) -> str:
    total = int(wait.total_seconds())
    return texts.BONUS_WAIT.format(hours=total // 3600, minutes=(total % 3600) // 60)


def _sub_text(user) -> str:
    if subscriptions.is_active(user):
        return texts.SUB_ACTIVE.format(plan=texts.PLAN_NAMES.get(user.sub_plan, user.sub_plan), until=user.sub_until.strftime("%d.%m.%Y"))
    return texts.SUB_NONE


def profile_kb() -> InlineKeyboardMarkup:
    return keyboards.grid(
        [], extra_rows=[[(texts.BTN_BUY_PACK, "shop:packs")], [(texts.BTN_BUY_SUB, "shop:subs")]]
    )


def packs_kb() -> InlineKeyboardMarkup:
    items = [(texts.PACK_BTN.format(n=p.crystals), f"buy:{p.code}") for p in PACKS]
    return keyboards.grid(items, cols=3)


def subs_kb() -> InlineKeyboardMarkup:
    items = [(texts.SUB_BTN.format(name=texts.PLAN_NAMES[p.code]), f"buy:{p.code}") for p in SUBS]
    return keyboards.grid(items, cols=1)


async def _try_send_bonus_card(bot, chat_id: int, user, settings) -> None:
    try:
        await send_bonus_card(bot, chat_id, user, settings)
    except Exception as e:
        logger.warning("bonus card send failed: {}", e)


@profile_router.message(F.text == texts.BTN_PROFILE)
async def show_profile(message: Message, user, settings):
    st = bonus.bonus_status(user, settings)
    bonus_txt = texts.BONUS_READY if st.ready else _fmt_wait(st.wait)
    await message.answer(
        texts.PROFILE.format(crystals=user.crystals, sub=_sub_text(user), bonus=bonus_txt),
        reply_markup=profile_kb(),
    )
    await _try_send_bonus_card(message.bot, user.id, user, settings)


@profile_router.callback_query(F.data == "shop:packs")
async def open_packs(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(texts.SHOP_PACKS, reply_markup=packs_kb())


@profile_router.callback_query(F.data == "shop:subs")
async def open_subs(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(texts.SHOP_SUBS, reply_markup=subs_kb())


@profile_router.callback_query(F.data == "bonus:claim")
async def claim_bonus_cb(cb: CallbackQuery, session, user, settings):
    res = await bonus.claim_bonus(session, user.id, settings)
    if isinstance(res, bonus.BonusStatus):
        await cb.answer(texts.BONUS_NOT_READY.format(when=_fmt_wait(res.wait)), show_alert=True)
        await cb.message.edit_reply_markup(reply_markup=None)
        return
    amount, balance = res
    await cb.answer()
    await cb.message.edit_caption(caption=texts.BONUS_CLAIMED.format(n=amount, balance=balance), reply_markup=None)
