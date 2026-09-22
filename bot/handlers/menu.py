from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from bot import keyboards, texts
from bot.bonus_card import send_bonus_card

menu_router = Router(name="menu")


@menu_router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, user, settings):
    await state.clear()
    await message.answer(texts.MENU, reply_markup=keyboards.main_menu())
    try:
        await send_bonus_card(message.bot, user.id, user, settings)
    except Exception as e:
        logger.warning("bonus card send failed: {}", e)


@menu_router.message(Command("cancel"))
@menu_router.message(F.text == texts.BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(texts.CANCELLED, reply_markup=keyboards.main_menu())


@menu_router.callback_query(F.data == "gen:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.answer(texts.CANCELLED, reply_markup=keyboards.main_menu())


@menu_router.message(F.text == texts.BTN_HELP)
async def help_msg(message: Message):
    await message.answer(texts.HELP)
