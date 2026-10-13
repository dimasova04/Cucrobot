"""Правила при старте: четыре страницы и кнопка «Принимаю»."""
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts


def rules_markup(page: int, *, accept: bool) -> InlineKeyboardMarkup:
    last = len(texts.RULE_PAGES) - 1
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=texts.BTN_HELP_PREV, callback_data=f"rules:page:{page - 1}"))
    if page < last:
        nav.append(InlineKeyboardButton(text=texts.BTN_HELP_NEXT, callback_data=f"rules:page:{page + 1}"))
    rows = [nav] if nav else []
    if accept:
        rows.append([InlineKeyboardButton(text=texts.RULES_ACCEPT_BTN, callback_data="rules:accept")])
    else:
        rows.append([InlineKeyboardButton(text=texts.BTN_LOOKS_BACK, callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_rules(message, page: int, *, accept: bool):
    await message.answer(texts.RULE_PAGES[page], reply_markup=rules_markup(page, accept=accept))


async def show_rules(message, page: int, *, accept: bool):
    text = texts.RULE_PAGES[page]
    markup = rules_markup(page, accept=accept)
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramAPIError:
        await message.answer(text, reply_markup=markup)
