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


def _quality_row(user) -> list[tuple[str, str]]:
    if subscriptions.is_active(user):
        other = "premium" if user.preferred_tier == "base" else "base"
        return [(
            texts.BTN_QUALITY_TOGGLE.format(quality=texts.MODEL_NAMES[user.preferred_tier], other=texts.MODEL_NAMES[other]),
            "profile:quality",
        )]
    return [(texts.BTN_QUALITY_LOCKED, "profile:quality_locked")]


def profile_kb(user) -> InlineKeyboardMarkup:
    return keyboards.grid(
        [], extra_rows=[_quality_row(user), [(texts.BTN_BUY_PACK, "shop:packs")], [(texts.BTN_BUY_SUB, "shop:subs")]]
    )


def _profile_text(user, settings) -> str:
    st = bonus.bonus_status(user, settings)
    bonus_txt = texts.BONUS_READY if st.ready else _fmt_wait(st.wait)
    quality_costs = texts.QUALITY_COSTS.format(base=settings.cost_base, premium=settings.cost_premium)
    return texts.PROFILE.format(
        crystals=user.crystals,
        sub=_sub_text(user),
        bonus=bonus_txt,
        quality=texts.MODEL_NAMES[user.preferred_tier],
        quality_costs=quality_costs,
    )


def price_label(code: str, settings) -> str:
    rub, stars = settings.rub_price(code), settings.stars_price(code)
    if rub > 0 and stars > 0:
        return texts.PRICE_BOTH.format(rub=rub, stars=stars)
    if rub > 0:
        return texts.PRICE_RUB.format(rub=rub)
    return texts.PRICE_STARS.format(stars=stars)


def packs_kb(settings) -> InlineKeyboardMarkup:
    items = [(texts.PACK_BTN.format(n=p.crystals, price=price_label(p.code, settings)), f"buy:{p.code}") for p in PACKS]
    return keyboards.grid(items, cols=3)


def subs_kb(settings) -> InlineKeyboardMarkup:
    items = [(texts.SUB_BTN.format(name=texts.PLAN_NAMES[p.code].capitalize(), price=price_label(p.code, settings)), f"buy:{p.code}") for p in SUBS]
    return keyboards.grid(items, cols=1)


async def _try_send_bonus_card(bot, chat_id: int, user, settings) -> None:
    try:
        await send_bonus_card(bot, chat_id, user, settings)
    except Exception as e:
        logger.warning("bonus card send failed: {}", e)


@profile_router.message(F.text == texts.BTN_PROFILE)
async def show_profile(message: Message, user, settings):
    await message.answer(_profile_text(user, settings), reply_markup=profile_kb(user))
    await _try_send_bonus_card(message.bot, user.id, user, settings)


@profile_router.callback_query(F.data == "menu:bonus")
async def cb_bonus(cb: CallbackQuery, user, settings):
    st = bonus.bonus_status(user, settings)
    if not st.ready:
        await cb.answer(texts.BONUS_NOT_READY.format(when=_fmt_wait(st.wait)), show_alert=True)
        return
    await cb.answer()
    await _try_send_bonus_card(cb.bot, user.id, user, settings)


@profile_router.callback_query(F.data == "menu:profile")
async def cb_profile(cb: CallbackQuery, user, settings):
    await cb.answer()
    await cb.message.answer(_profile_text(user, settings), reply_markup=profile_kb(user))
    await _try_send_bonus_card(cb.bot, user.id, user, settings)


@profile_router.callback_query(F.data == "profile:quality")
async def toggle_quality(cb: CallbackQuery, session, user, settings):
    if not subscriptions.is_active(user):
        await cb.answer(texts.MODEL_PREMIUM_LOCKED, show_alert=True)
        return
    user.preferred_tier = "premium" if user.preferred_tier == "base" else "base"
    await session.commit()
    await cb.answer()
    await cb.message.edit_text(_profile_text(user, settings), reply_markup=profile_kb(user))


@profile_router.callback_query(F.data == "profile:quality_locked")
async def quality_locked(cb: CallbackQuery):
    await cb.answer(texts.MODEL_PREMIUM_LOCKED, show_alert=True)


@profile_router.callback_query(F.data == "shop:packs")
async def open_packs(cb: CallbackQuery, settings):
    await cb.answer()
    await cb.message.answer(
        texts.SHOP_PACKS.format(premium=settings.cost_premium), parse_mode="HTML", reply_markup=packs_kb(settings)
    )


@profile_router.callback_query(F.data == "shop:subs")
async def open_subs(cb: CallbackQuery, settings):
    await cb.answer()
    daily = settings.bonus_sub_amount
    await cb.message.answer(
        texts.SHOP_SUBS.format(daily=daily, monthly=daily * 30), parse_mode="HTML", reply_markup=subs_kb(settings)
    )


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
