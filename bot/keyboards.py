from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from bot import texts
from bot.flow import result_buttons


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_CREATE), KeyboardButton(text=texts.BTN_PROFILE)],
            [KeyboardButton(text=texts.BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def intro_kb(webapp_url: str = "") -> InlineKeyboardMarkup:
    kb = grid(
        [(texts.BTN_INTRO_CREATE, "menu:create")],
        1,
        [
            [(texts.BTN_INTRO_PROFILE, "menu:profile"), (texts.BTN_INTRO_BONUS, "menu:bonus")],
            [(texts.BTN_INTRO_HELP, "menu:help")],
        ],
    )
    if webapp_url:
        kb.inline_keyboard.append(
            [InlineKeyboardButton(text=texts.BTN_WEBAPP, web_app=WebAppInfo(url=webapp_url))]
        )
    return kb


def rules_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.RULES_ACCEPT_BTN, callback_data="rules:accept")]]
    )


def grid(
    items: list[tuple[str, str]],
    cols: int = 2,
    extra_rows: list[list[tuple[str, str]]] | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in items[i : i + cols]]
        for i in range(0, len(items), cols)
    ]
    for r in extra_rows or []:
        rows.append([InlineKeyboardButton(text=t, callback_data=d) for t, d in r])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def yes_no_kb(yes_cb: str, no_cb: str, yes_text: str, no_text: str) -> InlineKeyboardMarkup:
    return grid([(yes_text, yes_cb), (no_text, no_cb)], cols=2)


def result_kb(data: dict) -> InlineKeyboardMarkup:
    return grid(result_buttons(data), cols=2)


def cancel_row() -> list[tuple[str, str]]:
    return [(texts.BTN_CANCEL, "gen:cancel")]
