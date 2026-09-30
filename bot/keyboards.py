from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from bot import texts


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_CREATE), KeyboardButton(text=texts.BTN_PROFILE)],
            [KeyboardButton(text=texts.BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def intro_kb(webapp_url: str = "") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=texts.BTN_INTRO_CREATE, callback_data="menu:create")],
        [
            InlineKeyboardButton(text=texts.BTN_INTRO_PROFILE, callback_data="menu:profile"),
            InlineKeyboardButton(text=texts.BTN_INTRO_BONUS, callback_data="menu:bonus"),
        ],
        [InlineKeyboardButton(text=texts.BTN_INTRO_HELP, callback_data="menu:help")],
    ]
    if webapp_url:
        buttons.append([InlineKeyboardButton(text=texts.BTN_WEBAPP, web_app=WebAppInfo(url=webapp_url))])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.BTN_RETRY_SCENE, callback_data="gen:retry"),
                InlineKeyboardButton(text=texts.BTN_CHANGE_SCENE, callback_data="gen:change_scene"),
            ],
            [
                InlineKeyboardButton(text=texts.BTN_CHANGE_ACTOR, callback_data="gen:change_actor"),
                InlineKeyboardButton(text=texts.BTN_DETAIL, callback_data="gen:detail"),
            ],
            [
                InlineKeyboardButton(text=texts.BTN_HD, callback_data="gen:hd"),
            ],
            [
                InlineKeyboardButton(text=texts.BTN_NEW_PHOTOSHOOT, callback_data="gen:new_photoshoot"),
            ],
        ]
    )


def back_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_BACK, callback_data="flow:back")],
            [InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data="flow:cancel")],
        ]
    )


def cancel_only_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data="flow:cancel")]
        ]
    )