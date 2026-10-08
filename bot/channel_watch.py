"""Админ снял пост — автору приходит сообщение в боте.

Telegram не присылает событие «пост в канале удалён». Тот же бот, что публиковал
кадр, пробует поставить ту же кнопку ещё раз: «message is not modified» значит,
что пост на месте. «message to edit not found» — его уже нет.
"""
import asyncio

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from loguru import logger
from sqlalchemy import select

from bot import keyboards, texts
from bot.refs_view import bot_username
from database.base import utcnow
from database.models import Generation
from services.referrals import CHANNEL_CODE, link_for

THERE = "there"
GONE = "gone"
UNKNOWN = "unknown"

SCAN_EVERY_SEC = 60
SCAN_BATCH = 25
PROBE_PAUSE_SEC = 0.35

_GONE_MARKERS = (
    "message to edit not found",
    "message to be edited not found",
    "message not found",
    "message_id_invalid",
)

_watch_task: asyncio.Task | None = None


def classify_probe(description: str) -> str:
    text = (description or "").lower()
    if "message is not modified" in text:
        return THERE
    if any(marker in text for marker in _GONE_MARKERS):
        return GONE
    return UNKNOWN


def _notice_lost(error: TelegramAPIError) -> bool:
    """Бот заблокирован или чата с автором уже нет — повторять нечего."""
    if isinstance(error, TelegramForbiddenError):
        return True
    text = error.message.lower()
    return any(bit in text for bit in (
        "bot was blocked",
        "user is deactivated",
        "chat not found",
        "peer_id_invalid",
    ))


async def probe_post(bot, chat_id, message_id: int, reply_markup) -> str:
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
        )
    except TelegramRetryAfter:
        raise
    except TelegramBadRequest as e:
        return classify_probe(e.message)
    except TelegramAPIError as e:
        logger.warning("channel probe failed for {}: {}", message_id, e)
        return UNKNOWN
    return THERE


async def _notify_removed(bot, user_id: int) -> bool:
    """True — уведомление ушло или его уже некому доставить."""
    try:
        await bot.send_message(user_id, texts.CHANNEL_REMOVED)
    except TelegramAPIError as e:
        if _notice_lost(e):
            logger.info("removal notice skipped for {}: {}", user_id, e)
            return True
        logger.warning("removal notice failed for {}: {}", user_id, e)
        return False
    return True


async def _due_posts(session, after_id: int, batch: int) -> list[Generation]:
    rows = await session.scalars(
        select(Generation)
        .where(
            Generation.channel_message_id.is_not(None),
            Generation.channel_removed_at.is_(None),
            Generation.id > after_id,
        )
        .order_by(Generation.id)
        .limit(batch)
    )
    return list(rows.all())


async def scan_removed_posts(
    bot,
    session_factory,
    chat_id,
    *,
    after_id: int = 0,
    batch: int = SCAN_BATCH,
    pause: float = PROBE_PAUSE_SEC,
) -> int:
    """Проверяет пачку постов. Возвращает id, с которого продолжить в следующий заход."""
    username = await bot_username(bot)
    if not username:
        return after_id
    markup = keyboards.channel_post_kb(link_for(username, CHANNEL_CODE))
    async with session_factory() as session:
        rows = await _due_posts(session, after_id, batch)
        if not rows and after_id:
            rows = await _due_posts(session, 0, batch)
            after_id = 0
        # Закрываем чтение, чтобы refresh увидел снятие, которое уже записал другой заход.
        await session.commit()
        next_id = after_id
        for gen in rows:
            message_id = gen.channel_message_id
            if message_id is None:
                continue
            try:
                status = await probe_post(bot, chat_id, message_id, markup)
            except TelegramRetryAfter as e:
                logger.warning("channel watch hit a limit: {}", e)
                break
            if status == GONE:
                await session.refresh(gen)
                if gen.channel_removed_at is not None:
                    next_id = gen.id
                    if pause:
                        await asyncio.sleep(pause)
                    continue
                if await _notify_removed(bot, gen.user_id):
                    gen.channel_removed_at = utcnow()
                    await session.commit()
            next_id = gen.id
            if pause:
                await asyncio.sleep(pause)
        return next_id


async def watch_channel_posts(bot, session_factory, chat_id) -> None:
    after_id = 0
    while True:
        try:
            after_id = await scan_removed_posts(bot, session_factory, chat_id, after_id=after_id)
        except Exception:
            logger.exception("channel watch failed")
        await asyncio.sleep(SCAN_EVERY_SEC)


def start_channel_watch(bot, session_factory, chat_id) -> None:
    global _watch_task
    if _watch_task is not None and not _watch_task.done():
        return
    _watch_task = asyncio.create_task(
        watch_channel_posts(bot, session_factory, chat_id),
        name="channel-watch",
    )
