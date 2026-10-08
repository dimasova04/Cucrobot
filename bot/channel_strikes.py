"""Счётчик 👎 в канале. На десяти пост удаляется, автору пишем в бот."""
from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import MessageReactionCountUpdated
from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from bot import texts
from database.base import utcnow
from database.models import Generation
from services.channel_strikes import (
    DOWNVOTES_TO_REMOVE,
    WARNINGS_FOR_BAN,
    Strike,
    downvote_total,
    format_ban_until,
    record_strike,
)

_ALREADY_GONE = (
    "message to delete not found",
    "message identifier is not specified",
    "message_id_invalid",
)


def strike_text(strike: Strike) -> str:
    if strike.warnings >= WARNINGS_FOR_BAN and strike.ban_until is not None:
        return texts.CHANNEL_STRIKE_BAN.format(until=format_ban_until(strike.ban_until))
    return texts.CHANNEL_STRIKE.format(n=strike.warnings)


def strike_router(settings, session_factory) -> Router:
    router = Router(name="channel_strikes")

    @router.message_reaction_count()
    async def on_reaction_counts(event: MessageReactionCountUpdated, bot: Bot):
        chat = settings.channel_chat()
        if not isinstance(chat, int) or event.chat.id != chat:
            return
        await handle_downvote_threshold(
            bot,
            session_factory,
            chat,
            event.message_id,
            downvote_total(event.reactions),
        )

    return router


async def delete_channel_message(bot, chat_id, message_id: int) -> bool:
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest as e:
        if any(bit in e.message.lower() for bit in _ALREADY_GONE):
            return True
        logger.warning("channel downvote delete failed for {}: {}", message_id, e)
        return False
    except TelegramAPIError as e:
        logger.warning("channel downvote delete failed for {}: {}", message_id, e)
        return False
    return True


async def _notify(bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except TelegramAPIError as e:
        logger.warning("downvote warning failed for {}: {}", user_id, e)


async def handle_downvote_threshold(bot, session_factory, chat_id, message_id: int, total: int) -> None:
    if total < DOWNVOTES_TO_REMOVE:
        return
    notice: tuple[int, str] | None = None
    should_delete = False
    async with session_factory() as session:
        gen = await session.scalar(
            select(Generation).where(
                Generation.channel_message_id == message_id,
                Generation.channel_removed_at.is_(None),
            )
        )
        if gen is None:
            struck = await session.scalar(
                select(Generation.id).where(Generation.channel_message_id == message_id)
            )
            should_delete = struck is not None
        else:
            try:
                strike = await record_strike(session, gen, utcnow())
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.info("downvote strike already recorded for message {}", message_id)
                strike = None
            should_delete = True
            if strike is not None:
                notice = (strike.user_id, strike_text(strike))
                logger.info(
                    "channel post {} removed after {} downvotes, warning {} for user {}",
                    message_id,
                    total,
                    strike.warnings,
                    strike.user_id,
                )
    if should_delete:
        await delete_channel_message(bot, chat_id, message_id)
    if notice is not None:
        await _notify(bot, notice[0], notice[1])
