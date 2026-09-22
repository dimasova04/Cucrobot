# tests/test_tribute.py
import hashlib
import hmac
import json

import pytest
from aiohttp.test_utils import make_mocked_request
from sqlalchemy import select

from bot import texts
from bot.handlers.tribute_webhook import make_handler
from config.settings import Settings
from database.models import Payment, User
from services.payments import tribute


def _settings(**kw):
    return Settings(_env_file=None, bot_token="x", tribute_api_key="secret", tribute_sub_month_id="offer_42", tribute_pack_100_id="prod_7", **kw)


def test_verify_signature():
    body = b'{"a":1}'
    sig = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert tribute.verify_signature(body, sig, "secret")
    assert tribute.verify_signature(body, "sha256=" + sig, "secret")
    assert not tribute.verify_signature(body, "bad", "secret")
    assert not tribute.verify_signature(body, sig, "")


def test_parse_subscription_by_id():
    body = {"name": "new_subscription", "payload": {"telegram_user_id": 5, "subscription_id": "offer_42", "period": "monthly", "amount": 49900, "currency": "rub", "payment_id": "p1"}}
    ev = tribute.parse_event(body, _settings())
    assert ev.kind == "sub" and ev.telegram_user_id == 5 and ev.product_code == "sub_month"
    assert ev.external_id == "p1" and ev.amount == 49900 and ev.currency == "rub"


def test_parse_subscription_fallback_by_period():
    body = {"name": "newSubscription", "payload": {"user": {"telegram_id": 6}, "subscription_id": "unknown", "period": "weekly", "id": 99}}
    ev = tribute.parse_event(body, _settings())
    assert ev.product_code == "sub_week"
    # id оффера не может служить id платежа: он одинаков у всех продлений
    assert ev.external_id != "99"
    assert ev.external_id.startswith("sub:6:")
    assert tribute.parse_event(body, _settings()).external_id == ev.external_id


def _sub(uid, expires_at):
    return {
        "name": "new_subscription",
        "payload": {"telegram_user_id": uid, "subscription_id": "offer_42", "period": "monthly", "expires_at": expires_at},
    }


def test_renewals_of_same_subscription_get_different_external_ids():
    first = tribute.parse_event(_sub(5, "2026-10-22T00:00:00Z"), _settings())
    renewal = tribute.parse_event(_sub(5, "2026-11-22T00:00:00Z"), _settings())
    assert first.product_code == renewal.product_code == "sub_month"
    assert first.external_id != renewal.external_id


def test_same_subscription_for_different_users_gets_different_external_ids():
    a = tribute.parse_event(_sub(5, "2026-10-22T00:00:00Z"), _settings())
    b = tribute.parse_event(_sub(6, "2026-10-22T00:00:00Z"), _settings())
    assert a.external_id != b.external_id


def test_parse_pack_by_name_and_other():
    body = {"name": "new_digital_product", "payload": {"telegram_user_id": 7, "product_id": "zzz", "product_name": "300 кристалликов", "transaction_id": "t1"}}
    ev = tribute.parse_event(body, _settings())
    assert ev.kind == "pack" and ev.product_code == "pack_300" and ev.external_id == "t1"
    ev2 = tribute.parse_event({"name": "cancelled_subscription", "payload": {"telegram_user_id": 7}}, _settings())
    assert ev2.kind == "other"


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def _req(body: dict, key: str = "secret", sig: str | None = None):
    raw = json.dumps(body).encode()
    sig = sig if sig is not None else hmac.new(key.encode(), raw, hashlib.sha256).hexdigest()
    req = make_mocked_request("POST", "/webhooks/tribute", headers={"trbt-signature": sig})

    async def read():
        return raw

    req.read = read
    return req


@pytest.mark.asyncio
async def test_handler_bad_signature(session_factory):
    settings = _settings(tribute_pack_50_id="p50")
    bot = FakeBot()
    handler = make_handler(session_factory, settings, bot)
    req = _req({"name": "new_digital_product", "payload": {}}, sig="bad")
    resp = await handler(req)
    assert resp.status == 401
    async with session_factory() as s:
        res = await s.execute(select(Payment))
        assert res.scalars().all() == []


@pytest.mark.asyncio
async def test_handler_grants_pack_and_notifies(session_factory):
    settings = _settings(tribute_pack_50_id="p50")
    bot = FakeBot()
    handler = make_handler(session_factory, settings, bot)
    body = {"name": "new_digital_product", "payload": {"product_id": "p50", "telegram_user_id": 5, "payment_id": "t1"}}
    resp = await handler(_req(body))
    assert resp.status == 200
    async with session_factory() as s:
        user = await s.get(User, 5)
        assert user.crystals == 50
        payments = (await s.execute(select(Payment))).scalars().all()
        assert len(payments) == 1
        assert payments[0].product == "pack_50"
    assert bot.sent == [(5, texts.PAYMENT_OK_PACK.format(n=50, balance=50))]


@pytest.mark.asyncio
async def test_handler_duplicate_request(session_factory):
    settings = _settings(tribute_pack_50_id="p50")
    bot = FakeBot()
    handler = make_handler(session_factory, settings, bot)
    body = {"name": "new_digital_product", "payload": {"product_id": "p50", "telegram_user_id": 5, "payment_id": "t1"}}
    await handler(_req(body))
    resp = await handler(_req(body))
    assert resp.status == 200
    text_body = resp.text if hasattr(resp, "text") else (await resp.read()).decode()
    assert text_body == "duplicate"
    async with session_factory() as s:
        user = await s.get(User, 5)
        assert user.crystals == 50
        payments = (await s.execute(select(Payment))).scalars().all()
        assert len(payments) == 1


@pytest.mark.asyncio
async def test_handler_unresolved_then_retryable(session_factory):
    settings = _settings(tribute_pack_50_id="p50")
    bot = FakeBot()
    handler = make_handler(session_factory, settings, bot)
    body_unresolved = {"name": "new_digital_product", "payload": {"product_id": "zzz", "product_name": "???", "telegram_user_id": 5, "payment_id": "t2"}}
    resp = await handler(_req(body_unresolved))
    assert resp.status == 200
    async with session_factory() as s:
        payments = (await s.execute(select(Payment))).scalars().all()
        assert len(payments) == 1
        assert payments[0].status == "unresolved"
        assert payments[0].external_id == "unresolved:t2"

    # retry after product id env vars are corrected -> now resolves and grants
    body_resolved = {"name": "new_digital_product", "payload": {"product_id": "p50", "telegram_user_id": 5, "payment_id": "t2"}}
    resp = await handler(_req(body_resolved))
    assert resp.status == 200
    async with session_factory() as s:
        user = await s.get(User, 5)
        assert user.crystals == 50


@pytest.mark.asyncio
async def test_handler_invalid_json_signed(session_factory):
    settings = _settings(tribute_pack_50_id="p50")
    bot = FakeBot()
    handler = make_handler(session_factory, settings, bot)
    raw = b"not-json"
    sig = hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
    req = make_mocked_request("POST", "/webhooks/tribute", headers={"trbt-signature": sig})

    async def read():
        return raw

    req.read = read
    resp = await handler(req)
    assert resp.status == 200
    text_body = resp.text if hasattr(resp, "text") else (await resp.read()).decode()
    assert text_body == "error-logged"
