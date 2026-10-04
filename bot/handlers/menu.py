from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from bot import keyboards, texts
from services import catalog
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


def _sample_list(names: list[str], limit: int, more_tpl: str, empty: str) -> str:
    if not names:
        return empty
    shown = ", ".join(names[:limit])
    rest = len(names) - limit
    return more_tpl.format(names=shown, n=rest) if rest > 0 else shown


@menu_router.callback_query(F.data == "menu:home")
async def cb_home(cb: CallbackQuery, state: FSMContext, user, settings):
    await state.clear()
    await cb.answer()
    await send_intro(cb.bot, user.id, settings.webapp_url, settings.channel_url)


async def build_help(session) -> str:
    actors = [a.name for a in await catalog.list_actors(session)]
    scenes = [s.name for s in await catalog.list_scenes(session)]
    return texts.HELP.format(
        actors=_sample_list(actors, 6, texts.HELP_ACTORS_MORE, texts.HELP_ACTORS_NONE),
        scenes=_sample_list(scenes, 8, texts.HELP_SCENES_MORE, texts.HELP_ACTORS_NONE),
    )


def _help_markup():
    return keyboards.grid([], extra_rows=[keyboards.back_row("menu")])


@menu_router.message(F.text == texts.BTN_HELP)
async def help_msg(message: Message, session):
    await message.answer(await build_help(session), parse_mode="HTML", reply_markup=_help_markup())


@menu_router.callback_query(F.data == "menu:help")
async def cb_help(cb: CallbackQuery, session):
    await cb.answer()
    await cb.message.answer(await build_help(session), parse_mode="HTML", reply_markup=_help_markup())
