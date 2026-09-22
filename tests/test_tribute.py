# tests/test_tribute.py
import hashlib
import hmac
import json

from config.settings import Settings
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
    assert ev.product_code == "sub_week" and ev.external_id == "99"


def test_parse_pack_by_name_and_other():
    body = {"name": "new_digital_product", "payload": {"telegram_user_id": 7, "product_id": "zzz", "product_name": "300 кристалликов", "transaction_id": "t1"}}
    ev = tribute.parse_event(body, _settings())
    assert ev.kind == "pack" and ev.product_code == "pack_300" and ev.external_id == "t1"
    ev2 = tribute.parse_event({"name": "cancelled_subscription", "payload": {"telegram_user_id": 7}}, _settings())
    assert ev2.kind == "other"
