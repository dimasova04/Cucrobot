from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from bot import keyboards, texts
from bot.refs_view import bot_username
from services import earn, invites

earn_router = Router(name="earn")


class EarnStates(StatesGroup):
    wallet = State()


def _kb(chat_url: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=texts.BTN_EARN_PAYOUT, callback_data="earn:payout")]]
    if chat_url:
        rows.append([InlineKeyboardButton(text=texts.BTN_EARN_CHAT, url=chat_url)])
    rows.append([InlineKeyboardButton(text=texts.BTN_LOOKS_BACK, callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_cabinet(session, bot, user, settings) -> tuple[str, InlineKeyboardMarkup]:
    cabinet = await earn.stats_for(session, user.id, settings.earn_rate_percent)
    username = await bot_username(bot)
    link = invites.invite_link(username, user.id)
    pending = ""
    if cabinet.pending_kop:
        pending = texts.EARN_PENDING_LINE.format(amount=earn.rub(cabinet.pending_kop))
    text = texts.EARN_CABINET.format(
        rate=settings.earn_rate_percent,
        link=link,
        regs=cabinet.registrations,
        pays=cabinet.payments,
        balance=earn.rub(cabinet.available_kop),
        pending=pending,
        minimum=settings.earn_min_rub,
    )
    return text, _kb(settings.referral_chat_url)


@earn_router.callback_query(F.data == "earn:open")
async def open_earn(cb: CallbackQuery, state: FSMContext, session, user, settings):
    await state.clear()
    await cb.answer()
    text, markup = await render_cabinet(session, cb.bot, user, settings)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@earn_router.callback_query(F.data == "earn:payout")
async def ask_payout(cb: CallbackQuery, state: FSMContext, session, user, settings):
    cabinet = await earn.stats_for(session, user.id, settings.earn_rate_percent)
    if cabinet.pending_kop:
        await cb.answer(texts.EARN_ALREADY, show_alert=True)
        return
    if cabinet.available_kop < settings.earn_min_rub * 100:
        await cb.answer(
            texts.EARN_LOW.format(balance=earn.rub(cabinet.available_kop), minimum=settings.earn_min_rub),
            show_alert=True,
        )
        return
    await state.set_state(EarnStates.wallet)
    await cb.answer()
    await cb.message.answer(
        texts.EARN_ASK,
        reply_markup=keyboards.grid([], extra_rows=[[(texts.BTN_LOOKS_BACK, "earn:open")]]),
    )


@earn_router.message(EarnStates.wallet, F.text)
async def got_wallet(message: Message, state: FSMContext, session, user, settings):
    parsed = earn.parse_payout_text(message.text or "")
    if parsed is None:
        await message.answer(texts.EARN_BAD)
        return
    username, wallet = parsed
    created = await earn.create_payout(
        session,
        user.id,
        username,
        wallet,
        rate_percent=settings.earn_rate_percent,
        min_rub=settings.earn_min_rub,
    )
    if created == "pending":
        await state.clear()
        await message.answer(texts.EARN_ALREADY)
        return
    if created == "low":
        await state.clear()
        cabinet = await earn.stats_for(session, user.id, settings.earn_rate_percent)
        await message.answer(
            texts.EARN_LOW.format(balance=earn.rub(cabinet.available_kop), minimum=settings.earn_min_rub)
        )
        return
    await state.clear()
    amount = earn.rub(created.amount_kop)
    await _tell_admins(message.bot, settings, created, amount)
    text, markup = await render_cabinet(session, message.bot, user, settings)
    await message.answer(texts.EARN_SENT.format(amount=amount))
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def _tell_admins(bot, settings, row, amount: str) -> None:
    admin_ids = list(getattr(settings, "admin_ids", None) or [])
    if bot is None or not admin_ids:
        return
    text = texts.EARN_ADMIN.format(
        username=row.tg_username,
        uid=row.user_id,
        amount=amount,
        wallet=row.wallet,
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.BTN_EARN_PAID, callback_data=f"earn:paid:{row.id}")]]
    )
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=markup)
        except Exception as e:
            logger.warning("earn payout notify to {} failed: {}", admin_id, e)


@earn_router.callback_query(F.data.startswith("earn:paid:"))
async def mark_paid_cb(cb: CallbackQuery, session, user, settings):
    if not settings.is_admin(user.id):
        await cb.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    payout_id = int(cb.data.rsplit(":", 1)[1])
    row = await earn.mark_paid(session, payout_id)
    if row is None:
        await cb.answer(texts.EARN_ALREADY_PAID, show_alert=True)
        return
    await cb.answer()
    amount = earn.rub(row.amount_kop)
    base = cb.message.text or ""
    await cb.message.edit_text(base + texts.EARN_ADMIN_DONE, reply_markup=None)
    try:
        await cb.bot.send_message(row.user_id, texts.EARN_PAID_USER.format(amount=amount))
    except Exception as e:
        logger.warning("earn paid notice to {} failed: {}", row.user_id, e)
