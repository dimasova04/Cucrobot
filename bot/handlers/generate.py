import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.keyboards import back_cancel_kb, result_kb
from database.models import Generation, User

logger = logging.getLogger(__name__)

# Объявляем роутер
generate_router = Router()


@generate_router.callback_query(F.data == "gen:detail")
async def detail_handler(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.answer(texts.ASK_DETAIL, reply_markup=back_cancel_kb())


@generate_router.callback_query(F.data == "gen:retry")
async def retry_handler(cb: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = cb.from_user.id

    stmt = select(User).where(User.telegram_id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or user.crystals < 1:
        await cb.answer(texts.NOT_ENOUGH.format(cost=1, balance=user.crystals if user else 0), show_alert=True)
        return

    await cb.answer()
    await cb.message.answer(texts.GENERATING)


@generate_router.callback_query(F.data == "gen:hd")
async def hd_handler(cb: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    gen_id = data.get("last_generation_id")

    if not gen_id:
        await cb.answer(texts.HD_EXPIRED, show_alert=True)
        return

    stmt = select(Generation).where(Generation.id == gen_id)
    result = await session.execute(stmt)
    generation = result.scalar_one_or_none()

    if not generation or not generation.result_url:
        await cb.answer(texts.HD_EXPIRED, show_alert=True)
        return

    await cb.answer()
    await cb.message.answer(f"📥 Ваше фото в высоком качестве:\n{generation.result_url}")