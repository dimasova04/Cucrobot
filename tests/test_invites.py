from types import SimpleNamespace

from sqlalchemy import select

from aiogram.filters import CommandObject

from bot import texts
from bot.handlers.balance import open_invite, profile_kb
from bot.handlers.start import accept_rules, cmd_start_deep_link
from config.settings import Settings
from database import repo
from database.base import utcnow
from database.models import CrystalTransaction, User
from services import invites, referrals
from services.billing import wallet


def _settings():
    return Settings(_env_file=None, bot_token="x")


class _State:
    def __init__(self):
        self.cleared = 0

    async def clear(self):
        self.cleared += 1


class _Msg:
    def __init__(self):
        self.answers = []

    async def answer(self, text, **kw):
        self.answers.append(text)


def test_payload_is_not_a_partner_code():
    assert invites.inviter_id_from_payload("inv_42") == 42
    assert invites.inviter_id_from_payload("inv_0") is None
    assert invites.inviter_id_from_payload("ref_blog") is None
    assert referrals.code_from_payload("inv_42") is None
    assert invites.invite_link("CucroBot", 42) == "https://t.me/CucroBot?start=inv_42"


def test_profile_offers_invite_after_pack():
    user = User(id=1, preferred_tier="base")
    cbs = [b.callback_data for row in profile_kb(user).inline_keyboard for b in row]
    assert cbs.index("shop:packs") < cbs.index("invite:open") < cbs.index("menu:home")


async def test_deep_link_remembers_only_a_new_user(session_factory):
    settings = _settings()
    async with session_factory() as s:
        host = await repo.get_or_create_user(s, 10, "host")
        host.rules_accepted_at = utcnow()
        fresh = await repo.get_or_create_user(s, 11, "new")
        stranger = await repo.get_or_create_user(s, 12, "old")
        stranger.rules_accepted_at = utcnow()
        newbie = await repo.get_or_create_user(s, 13, "self")
        other = await repo.get_or_create_user(s, 14, "other")
        other.rules_accepted_at = utcnow()

        msg = _Msg()
        await cmd_start_deep_link(msg, CommandObject(args="inv_10"), _State(), s, fresh, settings)
        assert fresh.invited_by == 10
        assert msg.answers == [texts.RULES]

        assert await invites.remember_inviter(s, stranger, 10) is False
        assert stranger.invited_by is None

        await cmd_start_deep_link(_Msg(), CommandObject(args="inv_13"), _State(), s, newbie, settings)
        assert newbie.invited_by is None

        unknown = await repo.get_or_create_user(s, 15, "ghost")
        assert await invites.remember_inviter(s, unknown, 999) is False
        assert unknown.invited_by is None

        unready = await repo.get_or_create_user(s, 16, "unready")
        assert await invites.remember_inviter(s, unready, 13) is False

        assert await invites.remember_inviter(s, fresh, 14) is False
        assert fresh.invited_by == 10


async def test_accept_pays_inviter_once(session_factory):
    settings = _settings()

    class Bot:
        def __init__(self):
            self.messages = []

        async def send_photo(self, chat_id, photo, **kw):
            return SimpleNamespace(photo=None)

        async def send_message(self, chat_id, text, **kw):
            self.messages.append((chat_id, text))

    class CbMsg:
        def __init__(self):
            self.answers = []

        async def answer(self, text, **kw):
            self.answers.append(text)

        async def edit_reply_markup(self, **kw):
            return None

    class Cb:
        def __init__(self, bot):
            self.bot = bot
            self.message = CbMsg()

        async def answer(self, *a, **k):
            return None

    async with session_factory() as s:
        host = await repo.get_or_create_user(s, 20, "host")
        host.rules_accepted_at = utcnow()
        friend = await repo.get_or_create_user(s, 21, "friend")
        friend.invited_by = 20
        bot = Bot()
        await accept_rules(Cb(bot), s, friend, settings)
        host = await repo.get_user(s, 20)
        friend = await repo.get_user(s, 21)
        assert friend.crystals == 3
        assert host.crystals == 3
        assert bot.messages == [(20, texts.INVITE_REWARDED.format(n=3, balance=3))]
        txs = (
            await s.execute(select(CrystalTransaction).where(CrystalTransaction.kind == "invite"))
        ).scalars().all()
        assert len(txs) == 1

        await accept_rules(Cb(bot), s, friend, settings)
        host = await repo.get_user(s, 20)
        assert host.crystals == 3
        assert len(bot.messages) == 1


async def test_reward_is_idempotent_and_skips_without_inviter(session_factory):
    settings = _settings()
    async with session_factory() as s:
        host = await repo.get_or_create_user(s, 30, "host")
        host.rules_accepted_at = utcnow()
        friend = await repo.get_or_create_user(s, 31, "friend")
        friend.rules_accepted_at = utcnow()
        friend.invited_by = 30
        assert await invites.reward_inviter(s, friend, settings) == (3, 3)
        assert await invites.reward_inviter(s, friend, settings) is None
        assert (await repo.get_user(s, 30)).crystals == 3

        solo = await repo.get_or_create_user(s, 32, "solo")
        assert await invites.reward_inviter(s, solo, settings) is None
        gone = await repo.get_or_create_user(s, 33, "gone")
        gone.invited_by = 404
        assert await invites.reward_inviter(s, gone, settings) is None


async def test_invite_screen_lists_rules_and_pack(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", None)
    settings = _settings()

    class Bot:
        async def me(self):
            return SimpleNamespace(username="CucroBot")

    class Msg:
        def __init__(self):
            self.sent = []

        async def answer(self, text, **kw):
            self.sent.append((text, kw))

    class Cb:
        def __init__(self):
            self.bot = Bot()
            self.message = Msg()

        async def answer(self, *a, **k):
            return None

    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 40, "u")
        cb = Cb()
        await open_invite(cb, user, settings)
    text, kw = cb.message.sent[0]
    assert "https://t.me/CucroBot?start=inv_40" in text
    assert "Правила:" in text
    assert "+3" in text
    assert "сначала купи пакет" in text
    rows = kw["reply_markup"].inline_keyboard
    assert rows[0][0].url.startswith("https://t.me/share/url?url=")
    assert "inv_40" in rows[0][0].url
    assert rows[1][0].callback_data == "shop:packs"
    assert rows[2][0].callback_data == "menu:profile"
    assert kw["parse_mode"] == "HTML"


async def test_zero_reward_does_not_pay(session_factory):
    settings = Settings(_env_file=None, bot_token="x", invite_crystals=0)
    async with session_factory() as s:
        host = await repo.get_or_create_user(s, 50, "host")
        friend = await repo.get_or_create_user(s, 51, "friend")
        friend.invited_by = 50
        assert await invites.reward_inviter(s, friend, settings) is None
        assert host.crystals == 0
        assert await wallet.get_balance(s, 50) == 0
