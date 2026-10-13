from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from bot import keyboards, texts
from bot.refs_view import bot_username

BANNER_PATH = Path(__file__).resolve().parent.parent / "assets" / "menu_banner.jpg"

_cached_file_id: str | None = None


async def _public_link(bot: Bot) -> str:
    try:
        username = await bot_username(bot)
    except Exception:
        username = ""
    if username:
        return f"https://t.me/{username}"
    return "https://t.me/cucro_bot"


async def send_intro(bot: Bot, chat_id: int, webapp_url: str = "", channel_url: str = "") -> None:
    """Главное меню: баннер + HTML-подпись + inline-кнопки. file_id кэшируется после первой отправки."""
    global _cached_file_id
    photo = _cached_file_id or FSInputFile(BANNER_PATH)
    sent = await bot.send_photo(
        chat_id,
        photo,
        caption=texts.INTRO.format(link=await _public_link(bot)),
        parse_mode="HTML",
        reply_markup=keyboards.intro_kb(webapp_url, channel_url),
    )
    if sent.photo:
        _cached_file_id = sent.photo[-1].file_id
