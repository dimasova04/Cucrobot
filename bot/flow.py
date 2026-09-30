import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.keyboards import back_cancel_kb, result_kb

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data == "gen:change_scene")
async def change_scene_handler(cb: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    # Сбрасываем кастомные детали, чтобы одежда с прошлой сцены не застревала
    data.pop("custom_detail", None)
    data["edit_mode"] = False
    await state.set_data(data)
    await cb.answer()
    
    await cb.message.answer(texts.CHOOSE_SCENE, reply_markup=back_cancel_kb())


@router.callback_query(F.data == "gen:new_photoshoot")
async def new_photoshoot_handler(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.answer(texts.SEND_PERSON_1)


@router.callback_query(F.data == "flow:back")
async def flow_back_handler(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.answer(texts.BACK_TO_RESULT, reply_markup=result_kb())


@router.callback_query(F.data == "flow:cancel")
async def flow_cancel_handler(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.answer(texts.CANCELLED)