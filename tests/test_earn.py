from types import SimpleNamespace

from bot import texts
from bot.handlers.earn import EarnStates, ask_payout, got_wallet, mark_paid_cb, open_earn
from config.settings import Settings
from database import repo
from database.base import utcnow
from database.models import Payment, ReferralPayout
from services import earn


TRC = "TXYZabcdefghjkmnpqrstuvwxyz1234567"
TON = "UQ" + "A" * 46


def _settings(**kw):
    return Settings(_env_file=None, bot_token="x", admin_ids=[7], earn_rate_percent=25, earn_min_rub=2000, **kw)


class _State:
    def __init__(self):
        self.cleared = False
        self._state = None

    async def clear(self):
        self.cleared = True
        self._state = None

    async def set_state(self, st):
        self._state = st


class _Bot:
    def __init__(self):
        self.sent = []

    async def me(self):
        return SimpleNamespace(username="CucroBot")

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text, reply_markup))


class _Msg:
    def __init__(self):
        self.answers = []
        self.edits = []
        self.text = ""

    async def answer(self, text, reply_markup=None, **kw):
        self.answers.append((text, reply_markup))

    async def edit_text(self, text, reply_markup=None, **kw):
        self.edits.append(text)
        self.text = text


class _Cb:
    def __init__(self, data, message, bot=None):
        self.data = data
        self.message = message
        self.bot = bot or _Bot()
        self.alerts = []

    async def answer(self, text=None, show_alert=False):
        self.alerts.append((text, show_alert))


def test_parse_payout_accepts_ton_and_trc20():
    assert earn.parse_payout_text(f"@nickname\n{TRC}") == ("nickname", TRC)
    assert earn.parse_payout_text(f"nickn {TON}") == ("nickn", TON)
    assert earn.parse_payout_text("nick Tshort") is None
    assert earn.parse_payout_text("@ab\n" + TRC) is None
    assert earn.parse_payout_text("/start") is None


def test_example_wallets_match_the_prompt():
    assert earn.parse_payout_text(texts.EARN_ASK.split("Пример:\n", 1)[1]) == (
        "nickname",
        "TXYZabcdefghjkmnpqrstuvwxyz1234567",
    )


async def _friend(session, friend_id, inviter_id, accepted=True):
    friend = await repo.get_or_create_user(session, friend_id, "friend")
    friend.invited_by = inviter_id
    friend.rules_accepted_at = utcnow() if accepted else None
    return friend


async def test_commission_is_a_quarter_of_ruble_payments(session_factory):
    async with session_factory() as s:
        inviter = await repo.get_or_create_user(s, 10, "host")
        inviter.rules_accepted_at = utcnow()
        await _friend(s, 11, 10)
        await _friend(s, 12, 10, accepted=False)
        stranger = await repo.get_or_create_user(s, 13, "other")
        stranger.rules_accepted_at = utcnow()
        s.add(Payment(provider="tribute", external_id="t1", user_id=11, product="pack_50", amount=158500, currency="rub"))
        s.add(Payment(provider="stars", external_id="s1", user_id=11, product="pack_50", amount=350, currency="XTR"))
        s.add(Payment(provider="tribute", external_id="t2", user_id=13, product="pack_50", amount=45000, currency="rub"))
        await s.commit()
        cabinet = await earn.stats_for(s, 10, 25)
    assert cabinet.registrations == 1
    assert cabinet.payments == 1
    assert cabinet.accrued_kop == 39625
    assert earn.rub(cabinet.available_kop) == "396.25 ₽"


async def test_payout_reserves_the_balance_until_admin_marks_it_paid(session_factory):
    async with session_factory() as s:
        await repo.get_or_create_user(s, 20, "host")
        await _friend(s, 21, 20)
        s.add(Payment(provider="tribute", external_id="t3", user_id=21, product="sub_month", amount=1_000_000, currency="rub"))
        await s.commit()
        low = await earn.create_payout(s, 20, "host", TRC, rate_percent=25, min_rub=2000)
        assert isinstance(low, ReferralPayout)
        assert low.amount_kop == 250_000
        again = await earn.create_payout(s, 20, "host", TRC, rate_percent=25, min_rub=2000)
        assert again == "pending"
        cabinet = await earn.stats_for(s, 20, 25)
        assert cabinet.available_kop == 0
        paid = await earn.mark_paid(s, low.id)
        assert paid.status == "paid"
        assert await earn.mark_paid(s, low.id) is None
        after = await earn.stats_for(s, 20, 25)
        assert after.available_kop == 0
        assert after.paid_kop == 250_000


async def test_small_balance_cannot_be_withdrawn(session_factory):
    async with session_factory() as s:
        await repo.get_or_create_user(s, 30, "host")
        await _friend(s, 31, 30)
        s.add(Payment(provider="tribute", external_id="t4", user_id=31, product="pack_50", amount=100_000, currency="rub"))
        await s.commit()
        assert await earn.create_payout(s, 30, "host", TRC, rate_percent=25, min_rub=2000) == "low"


async def test_cabinet_shows_link_and_payout_button(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", "CucroBot")
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 40, "host")
        user.rules_accepted_at = utcnow()
        await s.commit()
        message = _Msg()
        cb = _Cb("earn:open", message, _Bot())
        await open_earn(cb, _State(), s, user, _settings(referral_chat_url="https://t.me/refs"))
    text, markup = message.answers[-1]
    assert "https://t.me/CucroBot?start=inv_40" in text
    assert "25%" in text
    assert "2000" in text
    buttons = [b.callback_data or b.url for row in markup.inline_keyboard for b in row]
    assert buttons == ["earn:payout", "https://t.me/refs", "menu:home"]


async def test_order_asks_for_username_and_wallet_then_notifies_admin(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", "CucroBot")
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 50, "host")
        user.rules_accepted_at = utcnow()
        await _friend(s, 51, 50)
        s.add(Payment(provider="tribute", external_id="t5", user_id=51, product="sub_month", amount=1_000_000, currency="rub"))
        await s.commit()
        state = _State()
        message = _Msg()
        bot = _Bot()
        cb = _Cb("earn:payout", message, bot)
        await ask_payout(cb, state, s, user, _settings())
        assert state._state == EarnStates.wallet
        assert "Юзернейм" in message.answers[-1][0]
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 50, "host")
        state = _State()
        state._state = EarnStates.wallet
        message = _Msg()
        message.text = f"@cashier\n{TON}"
        bot = _Bot()
        message.bot = bot
        await got_wallet(message, state, s, user, _settings())
    assert state.cleared
    assert any("2500.00" in text for text, _ in message.answers)
    assert bot.sent[0][0] == 7
    note, markup = bot.sent[0][1], bot.sent[0][2]
    assert "@cashier" in note and TON in note and "2500.00" in note
    assert markup.inline_keyboard[0][0].callback_data.startswith("earn:paid:")


async def test_admin_paid_button_clears_the_referral_balance(session_factory):
    async with session_factory() as s:
        await repo.get_or_create_user(s, 60, "host")
        admin = await repo.get_or_create_user(s, 7, "admin")
        await _friend(s, 61, 60)
        s.add(Payment(provider="tribute", external_id="t6", user_id=61, product="sub_month", amount=1_000_000, currency="rub"))
        await s.commit()
        row = await earn.create_payout(s, 60, "cashier", TRC, rate_percent=25, min_rub=2000)
        await s.commit()
        message = _Msg()
        message.text = texts.EARN_ADMIN.format(username="cashier", uid=60, amount="2500.00 ₽", wallet=TRC)
        bot = _Bot()
        cb = _Cb(f"earn:paid:{row.id}", message, bot)
        await mark_paid_cb(cb, s, admin, _settings())
        fresh = await earn.stats_for(s, 60, 25)
    assert fresh.paid_kop == 250_000 and fresh.available_kop == 0
    assert "списан" in message.edits[-1]
    assert bot.sent[0][0] == 60
    assert cb.alerts == [(None, False)]


async def test_only_admin_can_mark_a_payout_paid(session_factory):
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 70, "host")
        await _friend(s, 71, 70)
        s.add(Payment(provider="tribute", external_id="t7", user_id=71, product="sub_month", amount=1_000_000, currency="rub"))
        await s.commit()
        row = await earn.create_payout(s, 70, "cashier", TRC, rate_percent=25, min_rub=2000)
        await s.commit()
        message = _Msg()
        cb = _Cb(f"earn:paid:{row.id}", message, _Bot())
        await mark_paid_cb(cb, s, user, _settings())
        still = await earn.stats_for(s, 70, 25)
    assert still.pending_kop == 250_000 and still.paid_kop == 0
    assert cb.alerts == [(texts.ADMIN_ONLY, True)]
    assert message.edits == []
