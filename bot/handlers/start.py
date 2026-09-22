from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot import keyboards, texts
from database.base import utcnow
from database.models import CrystalTransaction
from services.billing import wallet

start_router = Router(name="start")


@start_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user, settings):
    await state.clear()
    if user.rules_accepted_at is None:
        await message.answer(texts.RULES, reply_markup=keyboards.rules_kb())
        return
    await message.answer(texts.MENU, reply_markup=keyboards.main_menu())


@start_router.callback_query(F.data == "rules:accept")
async def accept_rules(cb: CallbackQuery, session, user, settings):
    if user.rules_accepted_at is None:
        user.rules_accepted_at = utcnow()
    has_start = (
        await session.execute(
            select(CrystalTransaction.id).where(
                CrystalTransaction.user_id == user.id, CrystalTransaction.kind == "start"
            )
        )
    ).scalar_one_or_none()
    granted = settings.start_crystals if has_start is None else 0
    if granted:
        await wallet.apply(session, user.id, granted, "start")
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(texts.WELCOME.format(n=granted), reply_markup=keyboards.main_menu())
