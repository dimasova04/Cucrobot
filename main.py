import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent, MenuButtonWebApp, WebAppInfo
from loguru import logger

from bot import texts
from bot.handlers.admin.router import build_admin_router
from bot.handlers.balance import profile_router
from bot.handlers.generate import generate_router
from bot.handlers.menu import menu_router
from bot.handlers.partner import partner_router
from bot.handlers.payments import payments_router
from bot.handlers.shop import shop_router
from bot.handlers.start import start_router
from bot.handlers.tribute_webhook import make_handler
from bot.middlewares import DbSessionMiddleware, RulesGateMiddleware
from bot.webapp_api import make_routes as make_webapp_routes
from bot.webhook_server import start_web_server
from config.settings import get_settings
from database.base import get_session_factory
from database.migrate import upgrade_to_head
from services import referrals
from services.catalog import seed_actors, seed_scenes
from services.generation.generator import Generator, TelegramFileFetcher, fail_stale_generations
from services.generation.runware_client import RunwareClient


class _Intercept(logging.Handler):
    def emit(self, record):
        logger.opt(depth=6, exception=record.exc_info).log(record.levelname, record.getMessage())


def _setup_logging():
    logger.remove()
    logger.add(sys.stdout, level="INFO")
    logging.basicConfig(handlers=[_Intercept()], level=logging.INFO, force=True)


def _storage(settings):
    if settings.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage
        ttl = settings.session_ttl_min * 60
        return RedisStorage.from_url(settings.redis_url, state_ttl=ttl, data_ttl=ttl)
    return MemoryStorage()


async def on_unhandled_error(event: ErrorEvent) -> bool:
    """Последняя линия: залогировать и не оставить пользователя без ответа."""
    logger.opt(exception=event.exception).error("unhandled update error")
    update = event.update
    cb = getattr(update, "callback_query", None)
    msg = getattr(update, "message", None)
    try:
        if cb is not None and cb.from_user is not None:
            await cb.answer(texts.GENERIC_ERROR, show_alert=True)
        elif msg is not None and msg.from_user is not None:
            await msg.answer(texts.GENERIC_ERROR)
    except Exception as e:
        logger.warning("failed to report error to user: {}", e)
    return True


def admin_commands() -> list[BotCommand]:
    return [
        BotCommand(command="admin", description=texts.CMD_ADMIN_DESC),
        BotCommand(command="stats", description=texts.CMD_STATS_DESC),
        BotCommand(command="actors", description=texts.CMD_ACTORS_DESC),
        BotCommand(command="scenes", description=texts.CMD_SCENES_DESC),
        BotCommand(command="user", description=texts.CMD_USER_DESC),
        BotCommand(command="give", description=texts.CMD_GIVE_DESC),
        BotCommand(command="sub", description=texts.CMD_SUB_DESC),
        BotCommand(command="block", description=texts.CMD_BLOCK_DESC),
        BotCommand(command="refs", description=texts.CMD_REFS_DESC),
        BotCommand(command="ref_add", description=texts.CMD_REF_ADD_DESC),
        BotCommand(command="ref_off", description=texts.CMD_REF_OFF_DESC),
        BotCommand(command="ref_on", description=texts.CMD_REF_ON_DESC),
    ]


async def set_menu_button(bot: Bot, settings) -> None:
    """Кнопка меню рядом с полем ввода открывает мини-приложение."""
    if not settings.webapp_url:
        return
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text=texts.WEBAPP_MENU_BUTTON, web_app=WebAppInfo(url=settings.webapp_url)
            )
        )
    except Exception as e:
        logger.warning("menu button not set: {}", e)


def build_dispatcher(settings, session_factory, generator: Generator | None) -> Dispatcher:
    dp = Dispatcher(storage=_storage(settings))
    dp["generator"] = generator
    dp.errors.register(on_unhandled_error)
    for obs in (dp.message, dp.callback_query, dp.pre_checkout_query):
        obs.middleware(DbSessionMiddleware(session_factory, settings))
    dp.message.middleware(RulesGateMiddleware())
    dp.callback_query.middleware(RulesGateMiddleware())
    # Роутеры: админские первыми, затем пользовательские. Роутеры с глобальными
    # кнопками и платежами идут до generate_router, у которого есть catch-all
    # хендлеры состояний.
    dp.include_router(build_admin_router(settings))
    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(profile_router)
    dp.include_router(shop_router)
    dp.include_router(payments_router)
    dp.include_router(partner_router)
    dp.include_router(generate_router)
    return dp


async def main():
    _setup_logging()
    settings = get_settings()
    # env.py внутри вызывает asyncio.run(), поэтому только в отдельном потоке.
    await asyncio.to_thread(upgrade_to_head)
    logger.info("migrations applied")
    sf = get_session_factory()
    async with sf() as s:
        added_scenes = await seed_scenes(s)
        added_actors = await seed_actors(s)
        await referrals.ensure_code(s, referrals.CHANNEL_CODE, "Канал")
        await s.commit()
    logger.info("seeded scenes: {} actors: {}", added_scenes, added_actors)
    logger.info("stale generations failed: {}", await fail_stale_generations(sf))

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=None))
    generator = Generator(sf, RunwareClient(settings.runware_api_key, settings.gen_timeout_sec), TelegramFileFetcher(bot), settings)
    dp = build_dispatcher(settings, sf, generator)
    user_commands = [
        BotCommand(command="start", description=texts.CMD_START_DESC),
        BotCommand(command="menu", description=texts.CMD_MENU_DESC),
        BotCommand(command="cancel", description=texts.CMD_CANCEL_DESC),
    ]
    await bot.set_my_commands(user_commands)
    # Админские команды видны в меню «/» только в чатах админов.
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(user_commands + admin_commands(), scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:  # админ ещё не открывал бота — Telegram отклонит scope
            logger.warning("admin commands for {} not set: {}", admin_id, e)
    await set_menu_button(bot, settings)
    routes = [("POST", settings.tribute_webhook_path, make_handler(sf, settings, bot))]
    if settings.webapp_url:
        routes += make_webapp_routes(sf, settings, bot)
    await start_web_server(routes, settings.webhook_port)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
