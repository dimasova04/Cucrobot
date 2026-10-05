import json
from datetime import timedelta

import pytest
from aiohttp.test_utils import make_mocked_request

from bot.webapp_api import make_routes
from config.settings import Settings
from database import repo
from database.base import utcnow
from database.models import Generation, Payment
from services import referrals
from tests.test_webapp_auth import TOKEN, make_init_data

ADMIN_ID = 607396740


class FakeBot:
    def __init__(self, username="CucroBot"):
        self.username = username
        self.invoices = []

    async def me(self):
        from types import SimpleNamespace

        return SimpleNamespace(username=self.username)

    async def create_invoice_link(self, **params):
        self.invoices.append(params)
        return "https://t.me/invoice/abc"


def _settings(**kw):
    kw.setdefault("admin_ids", [ADMIN_ID])
    return Settings(_env_file=None, bot_token=TOKEN, webapp_url="https://example.test/app", **kw)


@pytest.fixture(autouse=True)
def _reset_username_cache(monkeypatch):
    # bot_username кэшируется в модуле — не даём тестам протекать друг в друга.
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", None)


def _routes(session_factory, settings=None, bot=None):
    settings = settings or _settings()
    return {(m, p): h for m, p, h in make_routes(session_factory, settings, bot or FakeBot())}


def _req(method, path, user_id=5, body=None, auth=True, token=TOKEN):
    headers = {}
    if auth:
        headers["Authorization"] = "tma " + make_init_data(token, {"id": user_id, "username": "vasya"})
    req = make_mocked_request(method, path, headers=headers)

    async def _json():
        if body is None:
            raise ValueError("no body")
        return body

    req.json = _json
    return req


async def _call(routes, method, path, **kw):
    resp = await routes[(method, path)](_req(method, path, **kw))
    return resp.status, json.loads(resp.text)


async def _accepted_user(session_factory, user_id=5, **fields):
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, user_id, "vasya")
        user.rules_accepted_at = utcnow()
        for k, v in fields.items():
            setattr(user, k, v)
        await s.commit()


# ---------- авторизация ----------


async def test_me_requires_auth_header(session_factory):
    routes = _routes(session_factory)
    status, body = await _call(routes, "GET", "/api/me", auth=False)
    assert status == 401 and body == {"error": "auth"}


async def test_me_rejects_foreign_signature(session_factory):
    routes = _routes(session_factory)
    status, body = await _call(routes, "GET", "/api/me", token="99:OTHER")
    assert status == 401 and body == {"error": "auth"}


async def test_me_403_before_rules_accepted(session_factory):
    routes = _routes(session_factory)
    status, body = await _call(routes, "GET", "/api/me")
    assert status == 403 and body == {"error": "rules"}


async def test_me_403_for_blocked_user(session_factory):
    await _accepted_user(session_factory, is_blocked=True)
    routes = _routes(session_factory)
    status, body = await _call(routes, "GET", "/api/me")
    assert status == 403 and body == {"error": "blocked"}


# ---------- профиль ----------


async def test_me_returns_profile_fields(session_factory):
    await _accepted_user(session_factory, crystals=7)
    routes = _routes(session_factory)
    status, body = await _call(routes, "GET", "/api/me")
    assert status == 200
    assert body["id"] == 5 and body["crystals"] == 7 and body["username"] == "vasya"
    assert body["public_name"]
    assert body["level"] == "Новичок"
    assert body["sub"] == {"active": False, "plan": None, "until": None}
    assert body["bonus"]["ready"] is True and body["bonus"]["amount"] == 3
    assert body["quality"] == {"tier": "base", "can_premium": False}
    assert body["costs"] == {"base": 1, "premium": 3}
    assert body["is_admin"] is False and body["bot_username"] == "CucroBot"


async def test_me_shows_active_subscription(session_factory):
    until = utcnow() + timedelta(days=5)
    await _accepted_user(session_factory, sub_plan="sub_month", sub_until=until)
    routes = _routes(session_factory)
    _, body = await _call(routes, "GET", "/api/me")
    assert body["sub"]["active"] is True
    assert body["sub"]["plan"] == "sub_month"
    assert body["sub"]["until"] == until.strftime("%d.%m.%Y")
    assert body["quality"]["can_premium"] is True
    assert body["bonus"]["amount"] == 10


async def test_bonus_claim_happy_path_then_cooldown(session_factory):
    await _accepted_user(session_factory)
    routes = _routes(session_factory)
    status, body = await _call(routes, "POST", "/api/bonus/claim")
    assert status == 200 and body == {"ready": True, "claimed": 3, "balance": 3}
    async with session_factory() as s:
        assert (await repo.get_user(s, 5)).crystals == 3

    status, body = await _call(routes, "POST", "/api/bonus/claim")
    assert status == 200 and body["ready"] is False and body["wait_seconds"] > 0
    async with session_factory() as s:
        assert (await repo.get_user(s, 5)).crystals == 3


async def test_quality_premium_forbidden_without_subscription(session_factory):
    await _accepted_user(session_factory)
    routes = _routes(session_factory)
    status, body = await _call(routes, "POST", "/api/quality", body={"tier": "premium"})
    assert status == 403 and body == {"error": "premium_locked"}
    async with session_factory() as s:
        assert (await repo.get_user(s, 5)).preferred_tier == "base"


async def test_quality_switch_for_subscriber_and_bad_tier(session_factory):
    await _accepted_user(session_factory, sub_plan="sub_month", sub_until=utcnow() + timedelta(days=3))
    routes = _routes(session_factory)
    status, body = await _call(routes, "POST", "/api/quality", body={"tier": "premium"})
    assert status == 200 and body == {"tier": "premium"}
    async with session_factory() as s:
        assert (await repo.get_user(s, 5)).preferred_tier == "premium"

    status, body = await _call(routes, "POST", "/api/quality", body={"tier": "ultra"})
    assert status == 400 and body == {"error": "tier"}


# ---------- магазин ----------


async def test_shop_lists_six_products(session_factory):
    await _accepted_user(session_factory)
    settings = _settings(tribute_pack_50_url="https://t.me/tribute/pack50")
    routes = _routes(session_factory, settings)
    status, body = await _call(routes, "GET", "/api/shop")
    assert status == 200
    assert len(body["packs"]) == 3 and len(body["subs"]) == 3
    codes = [p["code"] for p in body["packs"] + body["subs"]]
    assert codes == ["pack_50", "pack_100", "pack_300", "sub_week", "sub_month", "sub_3month"]
    pack = body["packs"][0]
    assert pack["crystals"] == 50 and pack["gift"] == 0 and pack["stars"] == 350
    assert pack["tribute_url"] == "https://t.me/tribute/pack50"
    sub = body["subs"][1]
    assert sub["days"] == 30 and sub["gift"] == 20 and sub["rub"] == 1290 and sub["tribute_url"] == ""
    assert body["daily_bonus"] == 10


async def test_buy_stars_returns_invoice_link(session_factory):
    await _accepted_user(session_factory)
    bot = FakeBot()
    routes = _routes(session_factory, bot=bot)
    status, body = await _call(routes, "POST", "/api/buy/stars", body={"code": "pack_100"})
    assert status == 200 and body == {"invoice_link": "https://t.me/invoice/abc"}
    assert bot.invoices[0]["currency"] == "XTR"
    assert bot.invoices[0]["payload"] == "pack_100"
    assert bot.invoices[0]["prices"][0].amount == 650


async def test_buy_stars_rejects_unknown_product(session_factory):
    await _accepted_user(session_factory)
    routes = _routes(session_factory)
    status, body = await _call(routes, "POST", "/api/buy/stars", body={"code": "pack_999"})
    assert status == 400 and body == {"error": "product"}
    status, body = await _call(routes, "POST", "/api/buy/stars", body={})
    assert status == 400 and body == {"error": "product"}


# ---------- метрики ----------


async def test_admin_metrics_forbidden_for_regular_user(session_factory):
    await _accepted_user(session_factory)
    routes = _routes(session_factory)
    status, body = await _call(routes, "GET", "/api/admin/metrics")
    assert status == 403 and body == {"error": "admin"}


async def test_admin_metrics_for_admin(session_factory):
    await _accepted_user(session_factory, user_id=ADMIN_ID, crystals=4)
    async with session_factory() as s:
        await referrals.create_code(s, "blog", "Блогер", None, ADMIN_ID)
        user = await repo.get_user(s, ADMIN_ID)
        user.ref_code = "blog"
        user.ref_attributed_at = utcnow()
        s.add(Generation(user_id=ADMIN_ID, model_air="m", model_tier="base", actors=[], location="x", status="done", cost_usd=0.01))
        s.add(Payment(provider="stars", external_id="c1", user_id=ADMIN_ID, product="pack_50", amount=199, currency="XTR"))
        s.add(Payment(provider="tribute", external_id="t1", user_id=ADMIN_ID, product="sub_month", amount=59000, currency="rub"))
        await s.commit()

    routes = _routes(session_factory)
    status, body = await _call(routes, "GET", "/api/admin/metrics", user_id=ADMIN_ID)
    assert status == 200
    assert body["totals"]["users"] == 1 and body["totals"]["accepted"] == 1
    assert body["totals"]["generations_done"] == 1 and body["totals"]["crystals_in_wallets"] == 4
    assert body["totals"]["ref_users"] == 1
    assert body["today"]["stars"] == 199 and body["today"]["tribute_rub"] == 590
    assert body["today"]["generations"] == {"base": 1}
    assert body["week"]["new_users"] == 1 and body["month"]["new_users"] == 1

    assert len(body["daily"]) == 30
    today = body["daily"][-1]
    assert today["new_users"] == 1 and today["generations"] == 1
    assert today["stars"] == 199 and today["tribute_rub"] == 590
    assert body["daily"][0]["new_users"] == 0

    assert len(body["referrals"]) == 1
    ref = body["referrals"][0]
    assert ref["code"] == "blog" and ref["title"] == "Блогер" and ref["users"] == 1
    assert ref["paying_users"] == 1 and ref["stars"] == 199 and ref["tribute_rub"] == 590
    assert ref["link"] == "https://t.me/CucroBot?start=ref_blog"


# ---------- статика ----------


async def test_index_and_static_are_served(session_factory):
    routes = _routes(session_factory)
    resp = await routes[("GET", "/app")](make_mocked_request("GET", "/app"))
    assert resp.status == 200 and resp._path.name == "index.html"

    req = make_mocked_request("GET", "/app/static/app.js")
    req.match_info["filename"] = "app.js"
    resp = await routes[("GET", "/app/static/{filename}")](req)
    assert resp.status == 200 and resp._path.name == "app.js"


async def test_static_rejects_path_traversal(session_factory):
    from aiohttp import web

    routes = _routes(session_factory)
    for name in ("..", "nope.js"):
        req = make_mocked_request("GET", "/app/static/" + name)
        req.match_info["filename"] = name
        with pytest.raises(web.HTTPNotFound):
            await routes[("GET", "/app/static/{filename}")](req)
