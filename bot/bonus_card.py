from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from services.billing import bonus

BONUS_PHOTO_PATH = Path(__file__).resolve().parent.parent / "assets" / "bonus_crystals.jpg"

_cached_file_id: str | None = None


def _claim_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.BTN_BONUS_CLAIM, callback_data="bonus:claim")]]
    )


async def send_bonus_card(bot: Bot, chat_id: int, user, settings) -> None:
    """Присылает карточку бонуса фото + инлайн-кнопкой, если бонус готов к получению.

    file_id первой успешной отправки кэшируется в модуле и переиспользуется —
    Telegram не требует повторной загрузки файла.
    """
    global _cached_file_id
    status = bonus.bonus_status(user, settings)
    if not status.ready:
        return
    photo = _cached_file_id or FSInputFile(BONUS_PHOTO_PATH)
    sent = await bot.send_photo(
        chat_id,
        photo,
        caption=texts.BONUS_CARD.format(n=status.amount),
        reply_markup=_claim_kb(),
    )
    if sent.photo:
        _cached_file_id = sent.photo[-1].file_id
