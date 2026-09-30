import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from services.webapp_auth import strip_scheme, verify_init_data

TOKEN = "42:TEST-TOKEN"


def make_init_data(bot_token: str = TOKEN, user: dict | None = None, auth_date: int | None = None, **extra) -> str:
    """Подписанная initData — ровно так же, как её собирает Telegram."""
    params = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAEtest",
        "user": json.dumps(user or {"id": 5, "username": "vasya"}, separators=(",", ":"), ensure_ascii=False),
    }
    params.update(extra)
    data_check_string = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(params)


def test_valid_signature_returns_user():
    user = verify_init_data(make_init_data(), TOKEN)
    assert user is not None
    assert user["id"] == 5 and user["username"] == "vasya"


def test_extra_signed_fields_are_part_of_the_check():
    # Telegram добавляет поля (signature, chat_instance...) — они входят в подпись.
    data = make_init_data(signature="abc", chat_instance="-100500")
    assert verify_init_data(data, TOKEN) is not None


def test_tampered_payload_fails():
    data = make_init_data()
    tampered = data.replace("%22id%22%3A5", "%22id%22%3A6")
    assert tampered != data
    assert verify_init_data(tampered, TOKEN) is None


def test_wrong_token_fails():
    assert verify_init_data(make_init_data(), "99:OTHER") is None


def test_missing_hash_fails():
    assert verify_init_data("auth_date=1&user=%7B%22id%22%3A5%7D", TOKEN) is None


def test_expired_fails():
    old = int(time.time()) - 86_400 - 60
    data = make_init_data(auth_date=old)
    assert verify_init_data(data, TOKEN) is None
    # та же строка проходит, если окно достаточно широкое — значит дело именно в сроке
    assert verify_init_data(data, TOKEN, max_age_sec=10**7) is not None


def test_garbage_and_empty_input():
    assert verify_init_data("", TOKEN) is None
    assert verify_init_data("not a query string", TOKEN) is None
    assert verify_init_data(make_init_data(), "") is None
    assert verify_init_data(make_init_data(user={"username": "no-id"}), TOKEN) is None


def test_strip_scheme():
    assert strip_scheme("tma abc") == "abc"
    assert strip_scheme("TMA  abc ") == "abc"
    assert strip_scheme("Bearer abc") == ""
    assert strip_scheme(None) == ""
