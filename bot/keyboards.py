from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot import texts


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_CREATE), KeyboardButton(text=texts.BTN_BALANCE)],
            [KeyboardButton(text=texts.BTN_SHOP), KeyboardButton(text=texts.BTN_BONUS)],
            [KeyboardButton(text=texts.BTN_HELP)],
        ],
        resize_keyboard=True,
    )


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


def result_kb() -> InlineKeyboardMarkup:
    return grid(
        [
            (texts.BTN_MORE, "gen:more"),
            (texts.BTN_CHANGE_SCENE, "gen:change_scene"),
            (texts.BTN_CHANGE_ACTOR, "gen:change_actor"),
            (texts.BTN_NEW_PHOTO, "gen:new"),
        ],
        cols=2,
    )


def cancel_row() -> list[tuple[str, str]]:
    return [(texts.BTN_CANCEL, "gen:cancel")]
