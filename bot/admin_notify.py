from datetime import datetime

from loguru import logger

from bot import texts


def payment_money(provider: str, amount: int, currency: str) -> str:
    cur = (currency or "").lower()
    if provider == "stars" or cur == "xtr":
        return f"{int(amount)} ⭐ · Звёзды"
    return f"{int(amount) // 100} ₽ · СБП / карта"


def payment_who(user_id: int, username: str | None) -> str:
    if username:
        return f"@{username} · {user_id}"
    return str(user_id)


def payment_text(
    *,
    user_id: int,
    username: str | None,
    product_title: str,
    provider: str,
    amount: int,
    currency: str,
    balance: int,
    sub_until: datetime | None,
) -> str:
    until = ""
    if sub_until is not None:
        until = texts.ADM_PAYMENT_UNTIL.format(until=sub_until.strftime("%d.%m.%Y"))
    return texts.ADM_PAYMENT.format(
        who=payment_who(user_id, username),
        what=product_title,
        money=payment_money(provider, amount, currency),
        until=until,
        balance=balance,
    )


async def notify_admins_payment(bot, settings, **kwargs) -> None:
    """Пишет каждому админу о проведённой оплате. Сбой доставки одному не роняет остальных."""
    admin_ids = list(getattr(settings, "admin_ids", None) or [])
    if bot is None or not admin_ids:
        return
    text = payment_text(**kwargs)
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.warning("payment notify to {} failed: {}", admin_id, e)
