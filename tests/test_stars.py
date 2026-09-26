from types import SimpleNamespace

import pytest
from sqlalchemy import select

from config.settings import Settings
from database import repo
from database.models import Payment
from services.payments import stars


def test_invoice_params():
    s = Settings(_env_file=None, bot_token="x")
    p = stars.invoice_params("pack_50", s)
    assert p["currency"] == "XTR" and p["provider_token"] == "" and p["payload"] == "pack_50"
    assert p["prices"][0].amount == 199
    assert p["description"] == "+50 кристалликов"
    with pytest.raises(ValueError):
        stars.invoice_params("nope", s)


def test_parse_payload():
    assert stars.parse_payload("sub_month") == "sub_month"
    assert stars.parse_payload("garbage") is None


def test_generate_router_is_registered_last(dispatcher):
    names = [r.name for r in dispatcher.sub_routers]
    assert names[-1] == "generate"
    assert names.index("payments") < names.index("generate")
    assert names.index("profile") < names.index("generate")


class _FailingMessage:
    """Сообщение, у которого падает отправка подтверждения."""

    def __init__(self, sp):
        self.successful_payment = sp
        self.answers = []

    async def answer(self, text, **kw):
        self.answers.append(text)
        raise RuntimeError("telegram is down")


def _successful_payment(code="pack_50", charge_id="ch1"):
    return SimpleNamespace(
        invoice_payload=code,
        telegram_payment_charge_id=charge_id,
        total_amount=250,
        model_dump=lambda mode="json": {"charge": charge_id},
    )


async def test_stars_grant_survives_failed_confirmation(session_factory):
    from bot.handlers.payments import on_successful_payment

    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 1, "u")
        await s.commit()
    async with session_factory() as s:
        user = await repo.get_user(s, 1)
        message = _FailingMessage(_successful_payment())
        await on_successful_payment(message, s, user)
        assert message.answers  # отправка была и упала
        await s.rollback()  # как сделал бы DbSessionMiddleware при исключении
    async with session_factory() as s:
        assert (await repo.get_user(s, 1)).crystals == 50
        payments = (await s.execute(select(Payment))).scalars().all()
        assert [p.external_id for p in payments] == ["ch1"]


def test_pay_buttons_show_both_methods_clearly():
    from bot import texts
    from bot.handlers.balance import packs_kb, subs_kb
    from bot.handlers.shop import pay_kb
    from config.settings import Settings

    s = Settings(_env_file=None, bot_token="x", price_rub_sub_week=349, stars_sub_week=300,
                 tribute_sub_week_url="https://t.me/tribute/app?startapp=s17o6")
    labels = [b.text for row in pay_kb("sub_week", s).inline_keyboard for b in row]
    assert labels == ["💳 СБП / карта — 349 ₽", "⭐ Звёзды — 300 ⭐"]
    s2 = Settings(_env_file=None, bot_token="x", stars_pack_50=250)
    labels = [b.text for row in pay_kb("pack_50", s2).inline_keyboard for b in row]
    assert labels == ["⭐ Звёзды — 250 ⭐"]  # без ссылки Tribute кнопки карты нет
    sub_btns = [b.text for row in subs_kb(s).inline_keyboard for b in row]
    assert sub_btns[0] == "Неделя · +10 💎 в подарок"
    pack_btns = [b.text for row in packs_kb(s).inline_keyboard for b in row]
    assert pack_btns[0] == "50 💎"
    assert "СБП, карта или Telegram Stars" in texts.SHOP_SUBS
