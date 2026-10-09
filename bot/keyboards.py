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


def intro_kb(webapp_url: str = "", channel_url: str = "") -> InlineKeyboardMarkup:
    kb = grid(
        [(texts.BTN_INTRO_CREATE, "menu:create")],
        1,
        [
            [(texts.BTN_INTRO_PROFILE, "menu:profile"), (texts.BTN_INTRO_BONUS, "menu:bonus")],
            [(texts.BTN_INTRO_HELP, "menu:help")],
        ],
    )
    if channel_url:
        kb.inline_keyboard.append(
            [InlineKeyboardButton(text=texts.BTN_OPEN_CHANNEL, url=channel_url)]
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


def result_kb(data: dict, *, publish: bool = False, video_cost: int | None = None) -> InlineKeyboardMarkup:
    buttons = result_buttons(data)
    # «Оживить», «Опубликовать» и «Новая фотосессия» — каждая своей строкой.
    extra = []
    gen_id = data.get("last_generation_id")
    if video_cost and gen_id:
        extra.append([(texts.BTN_VIDEO.format(n=video_cost), f"gen:video:{gen_id}")])
    if publish and gen_id:
        extra.append([(texts.BTN_PUBLISH, "gen:publish")])
    extra.append([buttons[-1]])
    return grid(buttons[:-1], cols=2, extra_rows=extra)


def video_menu_kb(generation_id: int) -> InlineKeyboardMarkup:
    gid = str(generation_id)
    return grid(
        [
            (texts.BTN_VIDEO_AUTO, f"gen:v:auto:{gid}"),
            (texts.BTN_VIDEO_CLOSER, f"gen:v:closer:{gid}"),
            (texts.BTN_VIDEO_KISS, f"gen:v:kiss:{gid}"),
            (texts.BTN_VIDEO_HUG, f"gen:v:hug:{gid}"),
            (texts.BTN_VIDEO_DANCE, f"gen:v:dance:{gid}"),
            (texts.BTN_VIDEO_CUSTOM, f"gen:v:custom:{gid}"),
        ],
        2,
        [[(texts.BTN_CANCEL, "gen:video:cancel")]],
    )


def cancel_row() -> list[tuple[str, str]]:
    return [(texts.BTN_CANCEL, "gen:cancel")]


def back_row(target: str) -> list[tuple[str, str]]:
    """Строка «Назад» с явной целью: photo / actors / scenes / result."""
    return [(texts.BTN_BACK, f"nav:back:{target}")]


def channel_post_kb(bot_link: str) -> InlineKeyboardMarkup:
    """Кнопка под кадром в канале. Та же клавиатура нужна, чтобы проверить, что пост ещё на месте."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.BTN_CHANNEL_CREATE, url=bot_link),
    ]])
