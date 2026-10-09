from aiogram.types import BufferedInputFile

from bot import keyboards, texts
from bot.flow import validate_video_prompt
from bot.handlers.video import _run, open_video_menu, pick_video_action
from database import repo
from database.models import CrystalTransaction, Generation
from services.billing import wallet
from services.generation.content_filter import is_allowed, mentions_minor
from services.video.prompts import ACTIONS, video_prompt
from services.video.replicate_client import VideoError, seedance_input
from sqlalchemy import select


def test_custom_video_prompt_allows_adult_words_and_blocks_minors():
    assert validate_video_prompt("хочу секс и поцелуй") is None
    assert not is_allowed("хочу секс и поцелуй")
    assert validate_video_prompt("фото ребёнка") == texts.TEXT_REJECTED
    assert mentions_minor("a child walks in")
    assert validate_video_prompt("   ") == texts.VIDEO_PROMPT_EMPTY
    assert validate_video_prompt("а" * 2001) == texts.VIDEO_PROMPT_TOO_LONG
    assert "Animate this exact photo." in video_prompt("custom", "они целуются")
    assert "come alive" in ACTIONS["auto"]


def test_seedance_keeps_the_photo_and_asks_for_five_seconds():
    payload = seedance_input("https://example/frame.jpg", "wave", 5, "720p")
    assert payload["image"] == "https://example/frame.jpg"
    assert payload["duration"] == 5
    assert payload["resolution"] == "720p"
    assert payload["camera_fixed"] is False


def test_video_button_is_its_own_row_when_the_token_is_set():
    data = {"people": ["a"], "actors": [1], "last_generation_id": 7}
    plain = keyboards.result_kb(data)
    assert [b.callback_data for row in plain.inline_keyboard for b in row][-1] == "gen:new"
    assert "gen:video:7" not in [b.callback_data for row in plain.inline_keyboard for b in row]
    kb = keyboards.result_kb(data, video_cost=3, publish=True)
    assert [len(r) for r in kb.inline_keyboard] == [2, 2, 1, 1, 1, 1]
    assert kb.inline_keyboard[-3][0].callback_data == "gen:video:7"
    assert kb.inline_keyboard[-3][0].text == texts.BTN_VIDEO.format(n=3)
    menu = keyboards.video_menu_kb(7)
    cbs = [b.callback_data for row in menu.inline_keyboard for b in row]
    assert cbs == [
        "gen:v:auto:7", "gen:v:closer:7", "gen:v:kiss:7", "gen:v:hug:7",
        "gen:v:dance:7", "gen:v:custom:7", "gen:video:cancel",
    ]


class _Bot:
    async def download(self, file_id, destination):
        destination.write(b"jpeg-bytes")


class _Msg:
    def __init__(self):
        self.bot = _Bot()
        self.sent = []
        self.videos = []
        self.edits = []

    async def answer(self, text, reply_markup=None):
        self.sent.append((text, reply_markup))
        return self

    async def answer_video(self, file, caption=None):
        assert isinstance(file, BufferedInputFile)
        self.videos.append((file.data, caption))

    async def edit_text(self, text):
        self.edits.append(text)


class _Animator:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def animate(self, image, prompt, *, seconds, resolution):
        self.calls.append((image, prompt, seconds, resolution))
        if self.error:
            raise self.error
        return b"mp4"


def _settings():
    from config.settings import Settings
    return Settings(
        _env_file=None,
        bot_token="x",
        replicate_api_token="token",
        cost_video=3,
        video_seconds=5,
        video_resolution="720p",
    )


class _Cb:
    def __init__(self, message):
        self.message = message
        self.alerts = []
        self.data = ""

    async def answer(self, text=None, show_alert=False):
        self.alerts.append((text, show_alert))


class _State:
    def __init__(self):
        self.data = {}
        self.state = None

    async def set_state(self, state):
        self.state = state

    async def update_data(self, **kw):
        self.data.update(kw)


async def _ready(session, crystals=10):
    user = await repo.get_or_create_user(session, 5, "u")
    user.crystals = crystals
    gen = Generation(
        user_id=5, model_air="m", model_tier="base", actors=[], location="Офис",
        crystals_charged=1, status="done", result_file_id="photo-file",
    )
    session.add(gen)
    await session.commit()
    return gen.id


async def test_auto_video_charges_three_and_sends_the_clip(session_factory):
    async with session_factory() as s:
        gen_id = await _ready(s)
    animator = _Animator()
    msg = _Msg()
    async with session_factory() as s:
        user = await repo.get_user(s, 5)
        gen = await s.get(Generation, gen_id)
        await _run(msg, s, user, _settings(), gen, "auto", None, client=animator)
    assert animator.calls[0][0] == b"jpeg-bytes"
    assert "come alive" in animator.calls[0][1]
    assert animator.calls[0][2:] == (5, "720p")
    assert msg.videos == [(b"mp4", texts.VIDEO_CAPTION.format(seconds=5))]
    assert msg.edits[-1] == texts.CHARGED.format(cost=3, word="кристалла", balance=7)
    async with session_factory() as s:
        user = await repo.get_user(s, 5)
        assert user.crystals == 7


async def test_failed_video_returns_the_crystals(session_factory):
    async with session_factory() as s:
        gen_id = await _ready(s)
    msg = _Msg()
    async with session_factory() as s:
        user = await repo.get_user(s, 5)
        gen = await s.get(Generation, gen_id)
        await _run(msg, s, user, _settings(), gen, "kiss", None, client=_Animator(VideoError("failed")))
    assert msg.videos == []
    assert msg.edits[-1] == texts.VIDEO_FAILED
    async with session_factory() as s:
        user = await repo.get_user(s, 5)
        assert user.crystals == 10
        txs = (await s.execute(select(CrystalTransaction).where(CrystalTransaction.user_id == 5))).scalars().all()
        assert [t.kind for t in txs] == ["charge", "refund"]
        assert await wallet.refund_video(s, 5, txs[0].ref_id) is None


async def test_custom_action_asks_for_text_and_adult_prompt_is_sent(session_factory):
    async with session_factory() as s:
        gen_id = await _ready(s)
        user = await repo.get_user(s, 5)
    msg = _Msg()
    cb = _Cb(msg)
    cb.data = f"gen:v:custom:{gen_id}"
    state = _State()
    async with session_factory() as s:
        user = await repo.get_user(s, 5)
        await pick_video_action(cb, state, s, user, _settings())
    assert msg.sent[-1][0] == texts.VIDEO_ASK
    animator = _Animator()
    async with session_factory() as s:
        user = await repo.get_user(s, 5)
        gen = await s.get(Generation, gen_id)
        await _run(msg, s, user, _settings(), gen, "custom", "хочу секс на этом кадре", client=animator)
    assert "хочу секс на этом кадре" in animator.calls[0][1]
    async with session_factory() as s:
        assert (await repo.get_user(s, 5)).crystals == 7


async def test_menu_explains_the_price(session_factory):
    async with session_factory() as s:
        gen_id = await _ready(s)
    msg = _Msg()
    cb = _Cb(msg)
    cb.data = f"gen:video:{gen_id}"
    async with session_factory() as s:
        user = await repo.get_user(s, 5)
        await open_video_menu(cb, _State(), s, user, _settings())
    assert "5 секунд" in msg.sent[-1][0]
    assert "3 💎" in msg.sent[-1][0]
    assert msg.sent[-1][1].inline_keyboard[0][0].callback_data == f"gen:v:auto:{gen_id}"


async def test_empty_balance_does_not_call_the_model(session_factory):
    async with session_factory() as s:
        gen_id = await _ready(s, crystals=2)
    animator = _Animator()
    msg = _Msg()
    async with session_factory() as s:
        user = await repo.get_user(s, 5)
        gen = await s.get(Generation, gen_id)
        await _run(msg, s, user, _settings(), gen, "auto", None, client=animator)
    assert animator.calls == []
    assert "нужно 3" in msg.sent[-1][0]
    async with session_factory() as s:
        assert (await repo.get_user(s, 5)).crystals == 2
