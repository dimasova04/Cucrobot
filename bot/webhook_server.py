import os

from aiohttp import web
from loguru import logger


async def start_web_server(routes: list[tuple[str, str, object]], port: int) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/health", lambda _r: web.Response(text="ok"))
    for method, path, handler in routes:
        app.router.add_route(method, path, handler)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT") or port)
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info("web server on :{}", port)
    return runner
