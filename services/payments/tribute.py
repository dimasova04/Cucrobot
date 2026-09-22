# services/payments/tribute.py
import hashlib
import hmac
import json
import re
from dataclasses import dataclass

from services.billing.products import PRODUCTS

SUB_EVENTS = {"new_subscription", "newSubscription", "renewed_subscription", "renewedSubscription", "subscription_renewed"}
PACK_EVENTS = {"new_digital_product", "newDigitalProduct"}
PERIOD_MAP = {"weekly": "sub_week", "week": "sub_week", "monthly": "sub_month", "month": "sub_month", "quarterly": "sub_3month", "3month": "sub_3month", "3months": "sub_3month"}


def verify_signature(raw_body: bytes, signature_header: str, api_key: str) -> bool:
    if not api_key or not signature_header:
        return False
    expected = hmac.new(api_key.encode(), raw_body, hashlib.sha256).hexdigest()
    sig = signature_header.strip()
    if sig.startswith("sha256="):
        sig = sig[len("sha256="):]
    return hmac.compare_digest(expected, sig)


@dataclass
class TributeEvent:
    kind: str
    telegram_user_id: int | None
    external_id: str
    product_code: str | None
    amount: int
    currency: str
    raw: dict


def _first(payload: dict, *keys):
    for k in keys:
        v = payload.get(k)
        if v not in (None, ""):
            return v
    return None


def _user_id(payload: dict) -> int | None:
    v = _first(payload, "telegram_user_id", "user_id", "telegramUserId", "tg_user_id")
    if v is None and isinstance(payload.get("user"), dict):
        v = _first(payload["user"], "telegram_id", "telegramId", "id")
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _product_by_id(offer_id, settings) -> str | None:
    if offer_id is None:
        return None
    for code in PRODUCTS:
        if settings.tribute_id(code) and str(settings.tribute_id(code)) == str(offer_id):
            return code
    return None


def parse_event(body: dict, settings) -> TributeEvent:
    name = body.get("name") or body.get("event") or body.get("type") or ""
    payload = body.get("payload") or body
    kind = "sub" if name in SUB_EVENTS else "pack" if name in PACK_EVENTS else "other"
    uid = _user_id(payload)
    offer_id = _first(payload, "subscription_id", "subscriptionId", "offer_id", "offerId", "product_id", "productId")
    code = _product_by_id(offer_id, settings)
    if code is None and kind == "sub":
        code = PERIOD_MAP.get(str(payload.get("period", "")).lower())
    if code is None and kind == "pack":
        m = re.search(r"\b(50|100|300)\b", str(payload.get("product_name", "")))
        code = f"pack_{m.group(1)}" if m else None
    # Только идентификаторы самого платежа: "id" и "subscription_id" указывают на
    # оффер/подписку и повторяются у каждого продления, что склеило бы разные платежи
    # в один external_id и потеряло бы начисление.
    ext = _first(payload, "payment_id", "paymentId", "transaction_id", "transactionId")
    if ext is not None:
        external_id = str(ext)
    else:
        stamp = payload.get("created_at") or payload.get("expires_at") or ""
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
        ).hexdigest()[:16]
        external_id = f"{kind}:{uid}:{stamp}:{digest}"
    amount = payload.get("amount") or 0
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0
    return TributeEvent(kind, uid, external_id, code, amount, str(payload.get("currency", "")), body)
