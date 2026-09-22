import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from loguru import logger

from bot.handlers.balance import balance_router
from bot.handlers.generate import generate_router
from bot.handlers.menu import menu_router
from bot.handlers.payments import payments_router
from bot.handlers.shop import shop_router
from bot.handlers.start import start_router
from bot.handlers.tribute_webhook import make_handler
from bot.middlewares import DbSessionMiddleware, RulesGateMiddleware
from bot.webhook_server import start_web_server
from config.settings import get_settings
from database.base import get_session_factory, init_db
from services.catalog import seed_scenes_if_empty
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


def build_dispatcher(settings, session_factory, generator: Generator | None) -> Dispatcher:
    dp = Dispatcher(storage=_storage(settings))
    dp["generator"] = generator
    for obs in (dp.message, dp.callback_query, dp.pre_checkout_query):
        obs.middleware(DbSessionMiddleware(session_factory, settings))
    dp.message.middleware(RulesGateMiddleware())
    dp.callback_query.middleware(RulesGateMiddleware())
    # Роутеры: админские первыми, затем пользовательские (дополняется в задачах 9–12).
    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(generate_router)
    dp.include_router(balance_router)
    dp.include_router(shop_router)
    dp.include_router(payments_router)
    return dp


async def main():
    _setup_logging()
    settings = get_settings()
    await init_db()
    sf = get_session_factory()
    async with sf() as s:
        added = await seed_scenes_if_empty(s)
        await s.commit()
    logger.info("seeded scenes: {}", added)
    logger.info("stale generations failed: {}", await fail_stale_generations(sf))

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=None))
    generator = Generator(sf, RunwareClient(settings.runware_api_key, settings.gen_timeout_sec), TelegramFileFetcher(bot), settings)
    dp = build_dispatcher(settings, sf, generator)
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="menu", description="Меню"),
        BotCommand(command="cancel", description="Отмена"),
    ])
    routes = [("POST", settings.tribute_webhook_path, make_handler(sf, settings, bot))]
    await start_web_server(routes, settings.webhook_port)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
