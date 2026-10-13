from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from bot import keyboards, texts
from bot.bonus_card import send_bonus_card
from bot.intro import send_intro

menu_router = Router(name="menu")


@menu_router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, user, settings):
    await state.clear()
    await send_intro(message.bot, user.id, settings.webapp_url, settings.channel_url)
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


@menu_router.callback_query(F.data == "menu:home")
async def cb_home(cb: CallbackQuery, state: FSMContext, user, settings):
    await state.clear()
    await cb.answer()
    await send_intro(cb.bot, user.id, settings.webapp_url, settings.channel_url)


async def build_help(session) -> str:
    return texts.HELP


def _help_markup():
    return keyboards.grid([], extra_rows=[keyboards.back_row("menu")])


@menu_router.message(F.text == texts.BTN_HELP)
async def help_msg(message: Message, session):
    await message.answer(await build_help(session), parse_mode="HTML", reply_markup=_help_markup())


@menu_router.callback_query(F.data == "menu:help")
async def cb_help(cb: CallbackQuery, session):
    await cb.answer()
    await cb.message.answer(await build_help(session), parse_mode="HTML", reply_markup=_help_markup())


@menu_router.callback_query(F.data == "menu:rules")
async def cb_rules(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(texts.RULES, reply_markup=_help_markup())


@menu_router.callback_query(F.data == "menu:support")
async def cb_support(cb: CallbackQuery, settings):
    await cb.answer()
    text = texts.SUPPORT
    if settings.channel_url:
        text += f"\nКанал: {settings.channel_url}"
    await cb.message.answer(text, reply_markup=_help_markup())


@menu_router.callback_query(F.data == "menu:generate")
async def cb_generate(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.answer(texts.GEN_PICK, reply_markup=keyboards.generation_kb())
