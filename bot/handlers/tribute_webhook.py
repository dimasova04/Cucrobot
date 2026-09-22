# bot/handlers/tribute_webhook.py
import json

from aiohttp import web
from loguru import logger

from bot import texts
from database import repo
from database.models import Payment
from services.billing import grants
from services.payments import tribute


def make_handler(session_factory, settings, bot):
    async def handler(request: web.Request) -> web.Response:
        raw = await request.read()
        sig = request.headers.get("trbt-signature", "")
        if not tribute.verify_signature(raw, sig, settings.tribute_api_key):
            logger.error("tribute: bad signature headers={} body={}", dict(request.headers), raw[:500])
            return web.Response(status=401, text="bad signature")
        try:
            body = json.loads(raw)
            ev = tribute.parse_event(body, settings)
            logger.info("tribute event kind={} uid={} ext={} code={}", ev.kind, ev.telegram_user_id, ev.external_id, ev.product_code)
            if ev.kind == "other" or ev.telegram_user_id is None:
                logger.warning("tribute: unhandled event {}", body)
                return web.Response(text="ignored")
            async with session_factory() as s:
                user = await repo.get_or_create_user(s, ev.telegram_user_id, None)
                if ev.product_code is None:
                    if not await grants.payment_exists(s, "tribute", ev.external_id):
                        s.add(Payment(provider="tribute", external_id=ev.external_id, user_id=user.id, product="?", amount=ev.amount, currency=ev.currency, status="unresolved", raw=body))
                    await s.commit()
                    logger.error("tribute: cannot resolve product for {}", body)
                    return web.Response(text="unresolved")
                res = await grants.grant_product(s, "tribute", ev.external_id, user.id, ev.product_code, ev.amount, ev.currency, body)
                await s.commit()
            if res is None:
                logger.warning("tribute: duplicate {}", ev.external_id)
                return web.Response(text="duplicate")
            text = (
                texts.PAYMENT_OK_PACK.format(n=res.product.crystals, balance=res.balance)
                if res.product.kind == "pack"
                else texts.PAYMENT_OK_SUB.format(until=res.sub_until.strftime("%d.%m.%Y"))
            )
            try:
                await bot.send_message(ev.telegram_user_id, text)
            except Exception as e:  # user blocked bot etc.
                logger.warning("tribute: notify failed {}", e)
            return web.Response(text="ok")
        except Exception:
            logger.exception("tribute: handler error body={}", raw[:1000])
            return web.Response(text="error-logged")

    return handler
