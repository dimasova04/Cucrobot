from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger
from sqlalchemy import select

from bot import keyboards, texts
from bot.bonus_card import send_bonus_card
from bot.intro import send_intro
from database.base import utcnow
from database.models import CrystalTransaction
from database.repo import get_user_for_update
from services import invites, referrals
from services.billing import wallet

start_router = Router(name="start")

# Пейлоад диплинка из мини-приложения: t.me/<bot>?start=create
CREATE_PAYLOAD = "create"


async def _try_send_bonus_card(bot, chat_id: int, user, settings) -> None:
    try:
        await send_bonus_card(bot, chat_id, user, settings)
    except Exception as e:
        logger.warning("bonus card send failed: {}", e)


@start_router.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(message: Message, command: CommandObject, state: FSMContext, session, user, settings):
    """`/start ref_xxx` — привязка к партнёру до экрана правил: реферал
    засчитывается, даже если правила так и не примут.

    `/start create` — возврат из мини-приложения кнопкой «Сделать фото»:
    сразу открываем сценарий создания, без главного меню.
    """
    code = referrals.code_from_payload(command.args)
    if code is not None and await referrals.attribute(session, user, code):
        logger.info("user {} attributed to ref code {}", user.id, code)
    inviter_id = invites.inviter_id_from_payload(command.args)
    if inviter_id is not None and await invites.remember_inviter(session, user, inviter_id):
        logger.info("user {} remembered inviter {}", user.id, inviter_id)
    if command.args == CREATE_PAYLOAD and user.rules_accepted_at is not None:
        from bot.handlers.generate import start_create_flow

        await start_create_flow(message, state)
        return
    await cmd_start(message, state, user, settings)


@start_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user, settings):
    await state.clear()
    if user.rules_accepted_at is None:
        await message.answer(texts.RULES, reply_markup=keyboards.rules_kb())
        return
    await send_intro(message.bot, user.id, settings.webapp_url, settings.channel_url)
    await _try_send_bonus_card(message.bot, user.id, user, settings)


async def _tell_inviter(bot, inviter_id: int, amount: int, balance: int) -> None:
    try:
        await bot.send_message(inviter_id, texts.INVITE_REWARDED.format(n=amount, balance=balance))
    except Exception as e:
        logger.warning("invite reward notify failed: {}", e)


@start_router.callback_query(F.data == "rules:accept")
async def accept_rules(cb: CallbackQuery, session, user, settings):
    locked = await get_user_for_update(session, user.id)
    just_accepted = locked.rules_accepted_at is None
    if just_accepted:
        locked.rules_accepted_at = utcnow()
    has_start = (
        await session.execute(
            select(CrystalTransaction.id).where(
                CrystalTransaction.user_id == locked.id, CrystalTransaction.kind == "start"
            )
        )
    ).scalar_one_or_none()
    granted = settings.start_crystals if has_start is None else 0
    if granted:
        await wallet.apply(session, locked.id, granted, "start")
    rewarded = None
    if just_accepted:
        try:
            rewarded = await invites.reward_inviter(session, locked, settings)
        except Exception as e:
            logger.warning("invite reward failed: {}", e)
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    if granted:
        await cb.message.answer(texts.WELCOME.format(n=granted), reply_markup=keyboards.main_menu())
        await send_intro(cb.bot, locked.id, settings.webapp_url, settings.channel_url)
        await _try_send_bonus_card(cb.bot, locked.id, locked, settings)
    else:
        await cb.message.answer(texts.MENU, reply_markup=keyboards.main_menu())
        await send_intro(cb.bot, locked.id, settings.webapp_url, settings.channel_url)
    if rewarded is not None:
        amount, balance = rewarded
        await _tell_inviter(cb.bot, locked.invited_by, amount, balance)
