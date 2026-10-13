"""«Как это работает»: анимация, пример фото и пример ролика. Листается одной кнопкой."""
from pathlib import Path

from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo

from bot import texts

ROOT = Path(__file__).resolve().parent.parent

SLIDES = (
    {"kind": "video", "path": ROOT / "assets" / "help" / "intro.mp4", "caption": texts.HELP_TOUR_INTRO},
    {"kind": "photo", "path": ROOT / "assets" / "menu_banner.jpg", "caption": texts.HELP_TOUR_PHOTO},
    {"kind": "video", "path": ROOT / "assets" / "help" / "example.mp4", "caption": texts.HELP_TOUR_VIDEO},
)

_file_ids: dict[int, str] = {}


def help_kb(page: int) -> InlineKeyboardMarkup:
    last = len(SLIDES) - 1
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text=texts.BTN_HELP_PREV, callback_data=f"help:{page - 1}"))
    if page < last:
        row.append(InlineKeyboardButton(text=texts.BTN_HELP_NEXT, callback_data=f"help:{page + 1}"))
    else:
        row.append(InlineKeyboardButton(text=texts.BTN_GENERATION, callback_data="menu:generate"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def _source(page: int):
    return _file_ids.get(page) or FSInputFile(SLIDES[page]["path"])


def _remember(page: int, message) -> None:
    if message is None or message is True:
        return
    video = getattr(message, "video", None)
    if video is not None:
        _file_ids[page] = video.file_id
        return
    photo = getattr(message, "photo", None)
    if photo:
        _file_ids[page] = photo[-1].file_id


def _input(page: int):
    slide = SLIDES[page]
    media = _source(page)
    if slide["kind"] == "photo":
        return InputMediaPhoto(media=media, caption=slide["caption"])
    return InputMediaVideo(media=media, caption=slide["caption"], supports_streaming=True)


async def send_page(bot, chat_id: int, page: int):
    slide = SLIDES[page]
    media = _source(page)
    kb = help_kb(page)
    if slide["kind"] == "video":
        sent = await bot.send_video(
            chat_id, media, caption=slide["caption"], reply_markup=kb, supports_streaming=True
        )
    else:
        sent = await bot.send_photo(chat_id, media, caption=slide["caption"], reply_markup=kb)
    _remember(page, sent)
    return sent


async def show_page(message, page: int):
    """Листает то же сообщение. Если Telegram не дал заменить медиа — шлёт новое."""
    try:
        sent = await message.edit_media(_input(page), reply_markup=help_kb(page))
    except TelegramAPIError:
        sent = await send_page(message.bot, message.chat.id, page)
    else:
        _remember(page, sent)
    return sent
