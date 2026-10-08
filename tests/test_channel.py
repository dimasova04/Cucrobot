from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramServerError
from sqlalchemy import select

from bot import keyboards, texts
from bot.channel_watch import GONE, THERE, UNKNOWN, classify_probe, scan_removed_posts
from bot.handlers.balance import _profile_text, profile_kb
from bot.handlers.generate import gen_publish
from config.settings import Settings
from database import repo
from database.base import utcnow
from database.models import Generation, User
from services import aliases, referrals
from services.channel_rank import level_title, published_count


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, bot_token="x", **kw)


def test_channel_about_fits_telegram_limit():
    assert len(texts.CHANNEL_ABOUT) <= 255
    assert "Создать своё" in texts.CHANNEL_ABOUT
    assert "18+" in texts.CHANNEL_ABOUT


def test_pin_explains_the_three_scores_and_paid_reactions():
    from bot.channel_reactions import reactions_body

    pin = texts.CHANNEL_PIN
    assert "👍 — хорошо" in pin
    assert "👎 — не очень" in pin
    assert "🔥 — высшая оценка крутости" in pin
    assert "Платные реакции — по желанию" in pin
    assert "https://t.me/cucro_bot?start=channel" in pin
    assert len(pin) <= 1024
    body = reactions_body(-1004308497920)
    emojis = [item.get("emoji") for item in body["available_reactions"]]
    assert emojis == ["👍", "👎", "🔥", None]
    assert body["available_reactions"][-1] == {"type": "paid"}


def test_channel_chat_parses_id_and_stays_empty():
    live = _settings()
    assert live.channel_chat() == -1004308497920
    assert live.channel_url == "https://t.me/+Lqa_RWfiqC9kOWQy"
    assert _settings(channel_id="").channel_chat() is None
    assert _settings(channel_id="-100123").channel_chat() == -100123
    assert _settings(channel_id="@cucro").channel_chat() == "@cucro"


def test_channel_link_is_its_own_start_payload():
    assert referrals.code_from_payload("channel") == "channel"
    assert referrals.code_from_payload("abc") is None
    assert referrals.link_for("Cucrobot", "channel") == "https://t.me/Cucrobot?start=channel"
    assert referrals.link_for("Cucrobot", "blog") == "https://t.me/Cucrobot?start=ref_blog"


def test_channel_button_on_start_and_profile_only_when_linked():
    intro = keyboards.intro_kb(channel_url="https://t.me/+invite")
    assert intro.inline_keyboard[-1][0].url == "https://t.me/+invite"
    assert intro.inline_keyboard[-1][0].text == texts.BTN_OPEN_CHANNEL
    assert all(row[0].url is None for row in keyboards.intro_kb().inline_keyboard)

    user = User(id=1, preferred_tier="base", public_name="Lord M")
    kb = profile_kb(user, "https://t.me/+invite")
    urls = [b.url for row in kb.inline_keyboard for b in row]
    assert "https://t.me/+invite" in urls
    assert kb.inline_keyboard[-1][0].callback_data == "menu:home"
    plain = profile_kb(user)
    assert all(b.url is None for row in plain.inline_keyboard for b in row)

    shown = _profile_text(user, _settings())
    assert "Lord M" in shown
    assert "Уровень: Новичок" in shown
    assert "Уровень: Завсегдатай" in _profile_text(user, _settings(), published=10)
    unnamed = _profile_text(User(id=2, preferred_tier="base"), _settings())
    assert "В канале" not in unnamed


def test_publish_button_is_its_own_row():
    data = {"people": ["a"], "actors": [1], "last_generation_id": 7}
    kb = keyboards.result_kb(data, publish=True)
    assert [len(r) for r in kb.inline_keyboard] == [2, 2, 1, 1, 1]
    assert kb.inline_keyboard[-2][0].callback_data == "gen:publish"
    assert kb.inline_keyboard[-1][0].callback_data == "gen:new"
    without = keyboards.result_kb(data)
    assert [b.callback_data for row in without.inline_keyboard for b in row][-1] == "gen:new"
    assert "gen:publish" not in [b.callback_data for row in without.inline_keyboard for b in row]


async def test_alias_is_stable_and_unique(session_factory):
    async with session_factory() as s:
        first = await repo.get_or_create_user(s, 1, "a")
        second = await repo.get_or_create_user(s, 2, "b")
        one = await aliases.assign_public_name(s, first)
        again = await aliases.assign_public_name(s, first)
        other = await aliases.assign_public_name(s, second)
        await s.commit()
    assert one == again
    assert one != other
    assert one in aliases.NAMES and other in aliases.NAMES


async def test_channel_code_is_seeded_once(session_factory):
    async with session_factory() as s:
        created = await referrals.ensure_code(s, "channel", "Канал")
        await s.commit()
    assert created.code == "channel" and created.title == "Канал"
    async with session_factory() as s:
        again = await referrals.ensure_code(s, "channel", "Другое")
        assert again.title == "Канал"


class _State:
    def __init__(self, data):
        self.data = data

    async def get_data(self):
        return self.data


class _Bot:
    def __init__(self):
        self.photos = []

    async def send_photo(self, chat_id, photo, caption, reply_markup):
        self.photos.append((chat_id, photo, caption, reply_markup))
        return SimpleNamespace(message_id=55)

    async def me(self):
        return SimpleNamespace(username="Cucrobot")


class _Msg:
    def __init__(self):
        self.sent = []

    async def answer(self, text, reply_markup=None):
        self.sent.append(text)


class _Cb:
    def __init__(self, bot):
        self.bot = bot
        self.message = _Msg()
        self.alerts = []

    async def answer(self, text=None, show_alert=False):
        self.alerts.append((text, show_alert))


async def test_publish_sends_the_frame_once(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", "Cucrobot")
    async with session_factory() as s:
        await repo.get_or_create_user(s, 1, "u")
        gen = Generation(
            user_id=1, model_air="m", model_tier="base", actors=[], location="Офис",
            crystals_charged=1, status="done", result_file_id="photo-1",
        )
        s.add(gen)
        await s.commit()
        gen_id = gen.id

    settings = _settings(channel_id="-100777")
    bot = _Bot()
    cb = _Cb(bot)
    state = _State({"people": ["a"], "actors": [1], "scene_id": 3, "last_generation_id": gen_id})
    async with session_factory() as s:
        user = await repo.get_user(s, 1)
        await gen_publish(cb, state, s, user, settings)
        await s.commit()
        name = user.public_name

    assert bot.photos[0][0] == -100777
    assert bot.photos[0][1] == "photo-1"
    assert bot.photos[0][2] == texts.CHANNEL_POST.format(name=name, level="Новичок")
    button = bot.photos[0][3].inline_keyboard[0][0]
    assert button.text == "Создать своё"
    assert button.url == "https://t.me/Cucrobot?start=channel"
    assert cb.message.sent == [texts.CHANNEL_PUBLISHED.format(name=name, level="Новичок")]

    async with session_factory() as s:
        user = await repo.get_user(s, 1)
        await gen_publish(cb, state, s, user, settings)
    assert len(bot.photos) == 1
    assert cb.alerts[-1] == (texts.CHANNEL_ALREADY, True)


@pytest.mark.parametrize(
    ("count", "title"),
    [
        (0, "Новичок"),
        (1, "Новичок"),
        (9, "Новичок"),
        (10, "Завсегдатай"),
        (49, "Завсегдатай"),
        (50, "Мастер кадра"),
        (99, "Мастер кадра"),
        (100, "Легенда"),
        (299, "Легенда"),
        (300, "Гуру"),
        (1000, "Гуру"),
    ],
)
def test_level_rises_with_publications(count, title):
    assert level_title(count) == title


def test_channel_rules_fit_a_caption_and_link_the_bot():
    rules = texts.CHANNEL_RULES
    assert len(rules) <= 1024
    assert "обнажённые фото" in rules
    assert "жесть" in rules
    assert "Сделать свой кадр" in rules
    assert "https://t.me/cucro_bot?start=channel" in rules
    assert "18+" in rules
    assert "10 👎 снимают пост сами" in rules
    assert "Три предупреждения за неделю" in rules


def test_probe_tells_a_live_post_from_a_deleted_one():
    assert classify_probe("Bad Request: message is not modified") == THERE
    assert classify_probe("Bad Request: message to edit not found") == GONE
    assert classify_probe("Bad Request: MESSAGE_ID_INVALID") == GONE
    assert classify_probe("Bad Request: chat not found") == UNKNOWN
    assert classify_probe("Bad Request: not enough rights to manage chat") == UNKNOWN


def _bad(message: str):
    return TelegramBadRequest(None, message)


class _ProbeBot:
    def __init__(self, errors=None, send_error=None):
        self.errors = errors or {}
        self.send_error = send_error
        self.edits = []
        self.sent = []

    async def edit_message_reply_markup(self, *, chat_id, message_id, reply_markup):
        self.edits.append((chat_id, message_id, reply_markup))
        error = self.errors.get(message_id)
        if error:
            raise error

    async def send_message(self, chat_id, text):
        if self.send_error:
            raise self.send_error
        self.sent.append((chat_id, text))


async def _published(session, user_id, message_id, *, removed=False):
    session.add(Generation(
        user_id=user_id, model_air="m", model_tier="base", actors=[], location="Офис",
        crystals_charged=1, status="done", result_file_id="photo",
        channel_message_id=message_id,
        channel_removed_at=utcnow() if removed else None,
    ))


async def test_tenth_post_is_a_regular(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", "Cucrobot")
    async with session_factory() as s:
        await repo.get_or_create_user(s, 1, "u")
        for i in range(9):
            await _published(s, 1, 100 + i)
        fresh = Generation(
            user_id=1, model_air="m", model_tier="base", actors=[], location="Офис",
            crystals_charged=1, status="done", result_file_id="photo-10",
        )
        s.add(fresh)
        await s.commit()
        fresh_id = fresh.id

    bot = _Bot()
    cb = _Cb(bot)
    state = _State({"people": ["a"], "actors": [1], "scene_id": 3, "last_generation_id": fresh_id})
    async with session_factory() as s:
        user = await repo.get_user(s, 1)
        await gen_publish(cb, state, s, user, _settings(channel_id="-100777"))
        await s.commit()
        name = user.public_name
    assert bot.photos[0][2] == texts.CHANNEL_POST.format(name=name, level="Завсегдатай")


async def test_removed_posts_still_count_toward_the_level(session_factory):
    async with session_factory() as s:
        await repo.get_or_create_user(s, 1, "u")
        for i in range(10):
            await _published(s, 1, 200 + i, removed=True)
        await s.commit()
        assert await published_count(s, 1) == 10
        assert level_title(await published_count(s, 1)) == "Завсегдатай"


async def test_deleted_channel_post_notifies_the_author_once(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", "Cucrobot")
    async with session_factory() as s:
        await repo.get_or_create_user(s, 7, "u")
        await _published(s, 7, 55)
        await s.commit()

    bot = _ProbeBot({55: _bad("Bad Request: message to edit not found")})
    cursor = await scan_removed_posts(bot, session_factory, -100777, pause=0)
    assert cursor > 0
    assert bot.sent == [(7, texts.CHANNEL_REMOVED)]
    button = bot.edits[0][2].inline_keyboard[0][0]
    assert button.text == texts.BTN_CHANNEL_CREATE
    assert button.url == "https://t.me/Cucrobot?start=channel"
    async with session_factory() as s:
        gen = (await s.execute(select(Generation).where(Generation.channel_message_id == 55))).scalar_one()
        assert gen.channel_removed_at is not None
        assert gen.channel_message_id == 55

    again = _ProbeBot({55: _bad("Bad Request: message to edit not found")})
    await scan_removed_posts(again, session_factory, -100777, pause=0)
    assert again.edits == []
    assert again.sent == []


async def test_live_post_and_unknown_probe_do_not_notify(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", "Cucrobot")
    async with session_factory() as s:
        await repo.get_or_create_user(s, 7, "u")
        await _published(s, 7, 11)
        await _published(s, 7, 12)
        await s.commit()

    live = _ProbeBot({11: _bad("Bad Request: message is not modified")})
    await scan_removed_posts(live, session_factory, -100777, batch=1, pause=0)
    assert live.sent == []

    unknown = _ProbeBot({12: _bad("Bad Request: chat not found")})
    await scan_removed_posts(unknown, session_factory, -100777, after_id=0, pause=0)
    assert unknown.sent == []
    async with session_factory() as s:
        assert await published_count(s, 7) == 2
        rows = (await s.execute(select(Generation).where(Generation.user_id == 7))).scalars().all()
        assert all(row.channel_removed_at is None for row in rows)


async def test_blocked_author_is_marked_removed_without_a_retry(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", "Cucrobot")
    async with session_factory() as s:
        await repo.get_or_create_user(s, 7, "u")
        await _published(s, 7, 80)
        await s.commit()

    bot = _ProbeBot(
        {80: _bad("Bad Request: message to edit not found")},
        send_error=TelegramForbiddenError(None, "Forbidden: bot was blocked by the user"),
    )
    await scan_removed_posts(bot, session_factory, -100777, pause=0)
    assert bot.sent == []
    async with session_factory() as s:
        gen = (await s.execute(select(Generation).where(Generation.channel_message_id == 80))).scalar_one()
        assert gen.channel_removed_at is not None


async def test_failed_notice_is_retried(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", "Cucrobot")
    async with session_factory() as s:
        await repo.get_or_create_user(s, 7, "u")
        await _published(s, 7, 81)
        await s.commit()

    bot = _ProbeBot(
        {81: _bad("Bad Request: message to edit not found")},
        send_error=TelegramServerError(None, "Bad Gateway"),
    )
    await scan_removed_posts(bot, session_factory, -100777, pause=0)
    async with session_factory() as s:
        gen = (await s.execute(select(Generation).where(Generation.channel_message_id == 81))).scalar_one()
        assert gen.channel_removed_at is None
