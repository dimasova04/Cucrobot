from types import SimpleNamespace

from bot import keyboards, texts
from bot.handlers.balance import _profile_text, profile_kb
from bot.handlers.generate import gen_publish
from config.settings import Settings
from database import repo
from database.models import Generation, User
from services import aliases, referrals


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, bot_token="x", **kw)


def test_channel_about_fits_telegram_limit():
    assert len(texts.CHANNEL_ABOUT) <= 255
    assert "Создать своё" in texts.CHANNEL_ABOUT
    assert "18+" in texts.CHANNEL_ABOUT


def test_channel_chat_parses_id_and_stays_empty():
    assert _settings().channel_chat() is None
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
    assert bot.photos[0][2] == texts.CHANNEL_POST.format(name=name)
    button = bot.photos[0][3].inline_keyboard[0][0]
    assert button.text == "Создать своё"
    assert button.url == "https://t.me/Cucrobot?start=channel"
    assert cb.message.sent == [texts.CHANNEL_PUBLISHED.format(name=name)]

    async with session_factory() as s:
        user = await repo.get_user(s, 1)
        await gen_publish(cb, state, s, user, settings)
    assert len(bot.photos) == 1
    assert cb.alerts[-1] == (texts.CHANNEL_ALREADY, True)
