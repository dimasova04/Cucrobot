from datetime import timedelta

from bot import texts
from bot.handlers.balance import profile_kb, quality_locked, toggle_quality
from config.settings import Settings
from database import repo
from database.base import utcnow
from database.models import User


class _FakeCallback:
    def __init__(self):
        self.alerts: list[tuple[str | None, bool]] = []
        self.edits: list[tuple[str, object]] = []
        self.message = self

    async def answer(self, text=None, show_alert=False):
        self.alerts.append((text, show_alert))

    async def edit_text(self, text, reply_markup=None):
        self.edits.append((text, reply_markup))


def _settings() -> Settings:
    return Settings(_env_file=None, bot_token="x")


def _callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


async def test_opening_profile_assigns_the_channel_name(session_factory):
    from bot.handlers.balance import show_profile

    async with session_factory() as s:
        await repo.get_or_create_user(s, 1, "u")
        await s.commit()

    class Msg:
        def __init__(self):
            self.texts = []
            self.bot = None

        async def answer(self, text, reply_markup=None):
            self.texts.append(text)

    msg = Msg()
    async with session_factory() as s:
        user = await repo.get_user(s, 1)
        await show_profile(msg, s, user, _settings())
        await s.commit()
        name = user.public_name
    assert name
    assert f"В канале: {name}" in msg.texts[0]
    assert "Уровень: Новичок" in msg.texts[0]


def test_profile_kb_toggle_for_subscriber():
    subscriber = User(id=1, preferred_tier="base", sub_until=utcnow() + timedelta(days=1))
    cbs = _callbacks(profile_kb(subscriber))
    assert "profile:quality" in cbs
    assert "profile:quality_locked" not in cbs


def test_profile_kb_locked_for_non_subscriber():
    non_subscriber = User(id=2, preferred_tier="base")
    cbs = _callbacks(profile_kb(non_subscriber))
    assert "profile:quality_locked" in cbs
    assert "profile:quality" not in cbs


async def test_quality_toggle_flips_for_subscriber(session_factory):
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 1, "u")
        user.sub_until = utcnow() + timedelta(days=1)
        user.sub_plan = "sub_month"
        await s.commit()

    async with session_factory() as s:
        user = await repo.get_user(s, 1)
        assert user.preferred_tier == "base"
        cb = _FakeCallback()
        await toggle_quality(cb, s, user, _settings())
        assert user.preferred_tier == "premium"
        assert cb.alerts == [(None, False)]
        assert cb.edits and texts.MODEL_NAMES["premium"] in cb.edits[0][0]

        # toggling again flips back
        await toggle_quality(cb, s, user, _settings())
        assert user.preferred_tier == "base"

    async with session_factory() as s:
        # persisted through the commit inside the handler
        user = await repo.get_user(s, 1)
        assert user.preferred_tier == "base"


async def test_quality_toggle_refuses_for_non_subscriber(session_factory):
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 2, "u")
        await s.commit()

    async with session_factory() as s:
        user = await repo.get_user(s, 2)
        cb = _FakeCallback()
        await toggle_quality(cb, s, user, _settings())
        assert user.preferred_tier == "base"
        assert cb.alerts == [(texts.MODEL_PREMIUM_LOCKED, True)]
        assert cb.edits == []


async def test_quality_locked_button_shows_alert():
    cb = _FakeCallback()
    await quality_locked(cb)
    assert cb.alerts == [(texts.MODEL_PREMIUM_LOCKED, True)]
