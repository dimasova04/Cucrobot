"""Проверка initData из Telegram Mini App.

Клиент присылает строку initData в заголовке `Authorization: tma <initData>`.
Доверять можно только тому, что подписано ботом: id пользователя из тела запроса
не используется нигде.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

AUTH_SCHEME = "tma "


def strip_scheme(header: str | None) -> str:
    """initData из заголовка Authorization; пустая строка, если схема не та."""
    value = (header or "").strip()
    if not value.lower().startswith(AUTH_SCHEME):
        return ""
    return value[len(AUTH_SCHEME):].strip()


def verify_init_data(init_data: str, bot_token: str, max_age_sec: int = 86400) -> dict | None:
    """Проверяет подпись и свежесть initData. Возвращает dict пользователя или None.

    Никогда не логируем сам init_data: в нём подпись и данные пользователя.
    """
    if not init_data or not bot_token:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        return None

    try:
        auth_date = int(parsed.get("auth_date", ""))
    except ValueError:
        return None
    if max_age_sec > 0 and time.time() - auth_date > max_age_sec:
        return None

    try:
        user = json.loads(parsed.get("user", ""))
    except (ValueError, TypeError):
        return None
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        return None
    return user
