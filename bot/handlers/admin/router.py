from aiogram import Router

from bot.handlers.admin.actors import actors_router
from bot.handlers.admin.scenes import scenes_router
from bot.handlers.admin.stats import stats_router
from bot.middlewares import AdminOnlyMiddleware


def build_admin_router(settings) -> Router:
    admin_router = Router(name="admin")
    admin_router.message.middleware(AdminOnlyMiddleware(settings))
    admin_router.callback_query.middleware(AdminOnlyMiddleware(settings))
    admin_router.include_router(stats_router)
    admin_router.include_router(actors_router)
    admin_router.include_router(scenes_router)
    return admin_router
