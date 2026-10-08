"""JSON-API и статика мини-приложения (Telegram Mini App).

Живёт в том же aiohttp-приложении, что `/health` и вебхук Tribute.
Личность пользователя берётся только из подписанного initData — никаким
полям тела запроса доверять нельзя.
"""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiohttp import web
from loguru import logger

from bot.refs_view import bot_username
from database import repo
from services import aliases, referrals, stats
from services.channel_rank import level_title, published_count
from services.billing import bonus, subscriptions
from services.billing.products import PACKS, SUBS
from services.payments import stars as stars_service
from services.webapp_auth import strip_scheme, verify_init_data

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
DAILY_DAYS = 30


class ApiError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _read_json(request: web.Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _product_row(product, settings) -> dict:
    return {
        "code": product.code,
        "kind": product.kind,
        "title": product.title,
        "crystals": product.crystals if product.kind == "pack" else 0,
        "days": product.days,
        "gift": product.crystals if product.kind == "sub" else 0,
        "stars": settings.stars_price(product.code),
        "rub": settings.rub_price(product.code),
        "tribute_url": settings.tribute_url(product.code),
    }


def _me_payload(user, settings, username: str, published: int) -> dict:
    now = _now()
    st = bonus.bonus_status(user, settings, now)
    active = subscriptions.is_active(user, now)
    return {
        "id": user.id,
        "username": user.username or "",
        "public_name": user.public_name or "",
        "level": level_title(published) if user.public_name else "",
        "crystals": user.crystals,
        "sub": {
            "active": active,
            "plan": user.sub_plan if active else None,
            "until": user.sub_until.strftime("%d.%m.%Y") if active and user.sub_until else None,
        },
        "bonus": {
            "ready": st.ready,
            "amount": st.amount,
            "wait_seconds": int(st.wait.total_seconds()),
        },
        "quality": {"tier": user.preferred_tier, "can_premium": active},
        "costs": {"base": settings.cost_base, "premium": settings.cost_premium},
        "is_admin": settings.is_admin(user.id),
        "bot_username": username,
        "invite": {
            "reward": settings.invite_crystals,
            "link": f"https://t.me/{username}?start=inv_{user.id}" if username else "",
        },
    }


def make_routes(session_factory, settings, bot) -> list[tuple[str, str, object]]:
    async def _username() -> str:
        try:
            return await bot_username(bot)
        except Exception as e:  # Telegram недоступен — ссылка на бота просто не покажется
            logger.warning("webapp: bot username unavailable: {}", e)
            return ""

    def endpoint(fn, *, admin: bool = False):
        """Проверка initData → пользователь из БД → JSON. Ошибки в JSON, не в HTML."""

        async def handler(request: web.Request) -> web.Response:
            try:
                tg_user = verify_init_data(
                    strip_scheme(request.headers.get("Authorization")), settings.bot_token
                )
                if tg_user is None:
                    raise ApiError(401, "auth")
                async with session_factory() as session:
                    user = await repo.get_or_create_user(session, tg_user["id"], tg_user.get("username"))
                    if user.is_blocked:
                        raise ApiError(403, "blocked")
                    if user.rules_accepted_at is None:
                        raise ApiError(403, "rules")
                    if admin and not settings.is_admin(user.id):
                        raise ApiError(403, "admin")
                    payload = await fn(request, session, user)
                    await session.commit()
                return web.json_response(payload)
            except ApiError as e:
                return web.json_response({"error": e.code}, status=e.status)
            except Exception:
                logger.exception("webapp api error path={}", request.path)
                return web.json_response({"error": "server"}, status=500)

        return handler

    async def me(request, session, user):
        await aliases.assign_public_name(session, user)
        published = await published_count(session, user.id)
        return _me_payload(user, settings, await _username(), published)

    async def claim_bonus(request, session, user):
        res = await bonus.claim_bonus(session, user.id, settings)
        if isinstance(res, bonus.BonusStatus):
            return {"ready": False, "wait_seconds": int(res.wait.total_seconds())}
        amount, balance = res
        return {"ready": True, "claimed": amount, "balance": balance}

    async def set_quality(request, session, user):
        tier = (await _read_json(request)).get("tier")
        if tier not in ("base", "premium"):
            raise ApiError(400, "tier")
        if tier == "premium" and not subscriptions.is_active(user):
            raise ApiError(403, "premium_locked")
        locked = await repo.get_user_for_update(session, user.id)
        locked.preferred_tier = tier
        return {"tier": tier}

    async def shop(request, session, user):
        return {
            "packs": [_product_row(p, settings) for p in PACKS],
            "subs": [_product_row(p, settings) for p in SUBS],
            "daily_bonus": settings.bonus_sub_amount,
            "cost_base": settings.cost_base,
            "cost_premium": settings.cost_premium,
            "buy_stars_url": settings.tribute_buy_stars_url,
        }

    async def buy_stars(request, session, user):
        code = (await _read_json(request)).get("code")
        try:
            params = stars_service.invoice_params(code, settings)
        except (ValueError, AttributeError, TypeError):
            raise ApiError(400, "product") from None
        return {"invoice_link": await bot.create_invoice_link(**params)}

    async def metrics(request, session, user):
        now = _now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        totals = await stats.totals(session, now)
        windows = {
            "today": await stats.collect(session, today),
            "week": await stats.collect(session, now - timedelta(days=7)),
            "month": await stats.collect(session, now - timedelta(days=30)),
        }
        username = await _username()
        refs = []
        for st in await referrals.stats_all(session):
            row = asdict(st)
            row["link"] = referrals.link_for(username, st.code) if username else ""
            refs.append(row)
        return {
            "totals": asdict(totals),
            **{name: asdict(s) for name, s in windows.items()},
            "daily": await stats.daily_series(session, DAILY_DAYS, now),
            "referrals": refs,
        }

    async def index(request: web.Request) -> web.Response:
        return web.FileResponse(WEBAPP_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    async def static(request: web.Request) -> web.Response:
        name = request.match_info["filename"]
        path = (WEBAPP_DIR / name).resolve()
        if path.parent != WEBAPP_DIR or not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Cache-Control": "no-cache"})

    return [
        ("GET", "/app", index),
        ("GET", "/app/static/{filename}", static),
        ("GET", "/api/me", endpoint(me)),
        ("POST", "/api/bonus/claim", endpoint(claim_bonus)),
        ("POST", "/api/quality", endpoint(set_quality)),
        ("GET", "/api/shop", endpoint(shop)),
        ("POST", "/api/buy/stars", endpoint(buy_stars)),
        ("GET", "/api/admin/metrics", endpoint(metrics, admin=True)),
    ]
