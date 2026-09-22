from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import texts
from config.settings import Settings
from database import repo


def needs_rules(user, event) -> bool:
    if user.rules_accepted_at is not None:
        return False
    text = getattr(event, "text", None) or ""
    if text.startswith("/start"):
        return False
    if getattr(event, "data", None) == "rules:accept":
        return False
    return True


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory, settings: Settings):
        self._sf = session_factory
        self._settings = settings

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]):
        tg_user = getattr(event, "from_user", None)
        async with self._sf() as session:
            data["session"] = session
            data["settings"] = self._settings
            if tg_user is not None:
                data["user"] = await repo.get_or_create_user(session, tg_user.id, tg_user.username)
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class RulesGateMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]):
        user = data.get("user")
        if user is None:
            return await handler(event, data)
        if user.is_blocked:
            return None
        if needs_rules(user, event):
            if isinstance(event, Message):
                await event.answer(texts.RULES_REQUIRED)
            elif isinstance(event, CallbackQuery):
                await event.answer(texts.RULES_REQUIRED, show_alert=True)
            return None
        return await handler(event, data)


class AdminOnlyMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings):
        self._settings = settings

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]):
        tg_user = getattr(event, "from_user", None)
        if tg_user is None or not self._settings.is_admin(tg_user.id):
            if isinstance(event, Message):
                await event.answer(texts.ADMIN_ONLY)
            return None
        return await handler(event, data)
