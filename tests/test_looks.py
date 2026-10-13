from datetime import timedelta

from bot import texts
from bot.flow import GenStates, apply_catalog_scene, apply_look, empty_data
from bot.handlers import generate as generate_mod
from bot.looks import LOOKS, free_looks, get_look, locked_looks
from config.settings import Settings
from database import repo
from database.base import utcnow
from services.generation.content_filter import is_allowed, mentions_minor
from services.generation.generator import GenerationOutcome
from services.generation.prompt_builder import GenerationInput, build
from tests.test_generate_flow import _CapMessage, _FakeCb, _FakeGenerator, _FakeState, _FakeTarget, _callbacks


def test_photo_looks_match_the_example_and_skip_a_schoolgirl():
    ids = [item.id for item in LOOKS]
    assert len(ids) == len(set(ids))
    names = [item.name for item in LOOKS]
    assert names[0] == "Снять всё 😭"
    assert "Примерить бикини 👙" in names
    assert "Секретарша 👩‍💼" in names
    assert "Училка 👩‍🏫" in names
    assert "Зайка 🐰" in names
    assert get_look("strip").locked and get_look("stockings").locked and get_look("bdsm").locked
    assert not get_look("bikini").locked and not get_look("teacher").locked
    for item in LOOKS:
        assert item.prompt.startswith("[solo]")
        assert not mentions_minor(item.prompt)
        assert not mentions_minor(item.name)
        assert "школьн" not in item.name.lower() and "школьн" not in item.prompt.lower()
        assert len(f"look:{item.id}".encode()) <= 64
        assert len(item.name) <= 64
    for item in free_looks():
        assert is_allowed(item.prompt)
    for item in locked_looks():
        if item.id == "bdsm":
            assert "портупе" in item.prompt
        else:
            assert "без одежды" in item.prompt


def test_locked_look_stays_one_adult_woman():
    look = get_look("stockings")
    prompt, refs = build(
        GenerationInput(
            people=["p"], actors=[], scene_prompt=look.prompt, scene_ref=None,
            detail=None, width=832, height=1248,
        ),
        max_refs=4,
    )
    assert refs == ["p"]
    assert "Exactly 1 person in the frame" in prompt
    assert "чулк" in prompt


def test_catalog_scene_clears_the_look():
    data = empty_data()
    data["people"] = ["p"]
    apply_look(data, "strip", get_look("strip").prompt)
    assert data["look_id"] == "strip"
    apply_catalog_scene(data, 3)
    assert "look_id" not in data
    assert data["scene_id"] == 3
    assert data["custom_text"] is None


async def test_both_look_blocks_are_visible(session_factory):
    target, state = _FakeTarget(), _FakeState({"people": ["p"]}, GenStates.section)
    await generate_mod._show_looks(target, state)
    assert len(target.answers) == 1
    assert target.answers[0][0] == texts.CHOOSE_LOOKS
    rows = target.answers[0][1].inline_keyboard
    assert [b.callback_data for b in rows[0]] == ["look:prompt", "look:strip"]
    assert len(rows[0]) == 2
    cbs = _callbacks(target.answers[0][1])
    assert "look:bunny" in cbs and "look:bikini" in cbs and "look:stockings" in cbs
    assert "look:places" not in cbs and "scene:custom" not in cbs
    assert "shop:subs" not in cbs
    assert not any(item.startswith("look:page:") for item in cbs)
    assert rows[-1][0].text == texts.BTN_LOOKS_BACK
    assert rows[-1][0].callback_data == "nav:back:menu"
    assert state._state == GenStates.scene


def test_looks_pager_puts_the_number_opposite_the_arrow():
    items = [(str(i), f"look:{i}") for i in range(15)]
    first = generate_mod.looks_markup(items, 0, per_page=14).inline_keyboard
    assert [b.text for b in first[-2]] == ["1/2", texts.BTN_LOOKS_NEXT]
    assert [b.callback_data for b in first[-2]] == ["nav:noop", "look:page:1"]
    second = generate_mod.looks_markup(items, 1, per_page=14).inline_keyboard
    assert [b.text for b in second[-2]] == [texts.BTN_LOOKS_PREV, "2/2"]
    assert [b.callback_data for b in second[-2]] == ["look:page:0", "nav:noop"]
    assert second[-1][0].callback_data == "nav:back:menu"


async def test_looks_page_edits_the_same_message():
    class _Edit(_FakeTarget):
        def __init__(self):
            super().__init__()
            self.edits = []

        async def edit_text(self, text, reply_markup=None, **kw):
            self.edits.append((text, reply_markup))

    target = _Edit()
    state = _FakeState({"people": ["p"]}, GenStates.scene)
    cb = _FakeCb("look:page:1", target)
    await generate_mod.looks_page(cb, state)
    assert cb.answered == [(None, False)]
    assert target.edits[0][0] == texts.CHOOSE_LOOKS
    assert target.answers == []


async def test_free_prompt_asks_for_text():
    message = _CapMessage()
    state = _FakeState({"people": ["p"]}, GenStates.scene)
    cb = _FakeCb("look:prompt", message)
    await generate_mod.look_prompt(cb, state)
    assert message.answers[-1][0] == texts.LOOK_PROMPT
    assert state._state == GenStates.custom_scene
    assert cb.answered == [(None, False)]


async def test_section_label_does_nothing():
    message = _CapMessage()
    cb = _FakeCb("nav:noop", message)
    await generate_mod.nav_noop(cb)
    assert cb.answered == [(None, False)]
    assert message.answers == []


async def test_locked_look_without_subscription_opens_paywall(session_factory):
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 94, "u")
        user.crystals = 10
        user.sub_until = None
        await s.commit()
        state = _FakeState(
            {"people": ["p1"], "actors": [], "mode": "photo", "scene_id": None},
            GenStates.scene,
        )
        message = _CapMessage()
        cb = _FakeCb("look:strip", message)
        settings = Settings(_env_file=None, bot_token="x", admin_ids=[])
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=1, image_bytes=b"IMG", cost_usd=0, error=None)
        )
        await generate_mod.look_chosen(cb, state, s, user, settings, generator)
    assert generator.calls == []
    assert "подписк" in message.answers[-1][0].lower()
    buttons = _callbacks(message.answers[-1][1])
    assert any(item.startswith("buy:sub_") for item in buttons)
    assert state._data.get("look_id") is None


async def test_admin_without_subscription_opens_a_locked_look(session_factory, monkeypatch):
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 95, "u")
        user.crystals = 10
        user.sub_until = None
        await s.commit()
        state = _FakeState(
            {"people": ["p1"], "actors": [], "mode": "photo", "scene_id": None,
             "custom_text": None, "custom_file_id": None, "detail": None},
            GenStates.scene,
        )

        class _Photo(_CapMessage):
            def __init__(self):
                super().__init__()
                self.photos = []

            async def answer_photo(self, photo, caption=None, reply_markup=None, **kw):
                self.photos.append(caption)

        message = _Photo()
        cb = _FakeCb("look:strip", message)
        settings = Settings(_env_file=None, bot_token="x", admin_ids=[95], cost_base=1, cost_premium=3)
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=4, image_bytes=b"IMG", cost_usd=0.04, error=None, seed=1)
        )
        monkeypatch.setattr("bot.handlers.generate.watermark.apply_free_mark", lambda data: data)
        await generate_mod.look_chosen(cb, state, s, user, settings, generator)
    assert generator.calls[0].custom_scene_text.startswith("[solo]")
    assert "без одежды" in generator.calls[0].custom_scene_text
    assert message.photos == [texts.PHOTO_SCENE_CAPTION.format(scene="Снять всё 😭")]


async def test_subscriber_can_pick_a_locked_look(session_factory, monkeypatch):
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 96, "u")
        user.crystals = 10
        user.sub_until = utcnow() + timedelta(days=3)
        await s.commit()
        state = _FakeState(
            {"people": ["p1"], "actors": [], "mode": "photo", "scene_id": None,
             "custom_text": None, "custom_file_id": None, "detail": None},
            GenStates.scene,
        )

        class _Photo(_CapMessage):
            async def answer_photo(self, photo, caption=None, reply_markup=None, **kw):
                return None

        message = _Photo()
        cb = _FakeCb("look:stockings", message)
        settings = Settings(_env_file=None, bot_token="x", admin_ids=[], cost_base=1, cost_premium=3)
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=5, image_bytes=b"IMG", cost_usd=0.04, error=None, seed=1)
        )
        await generate_mod.look_chosen(cb, state, s, user, settings, generator)
    assert "чулк" in generator.calls[0].custom_scene_text
    assert state._data["look_id"] == "stockings"


def test_video_refs_are_optional_until_a_file_is_added():
    from bot.clips import get_clip, hard_clips, light_clips, ref_file
    from services.generation.content_filter import is_allowed as allowed

    assert [item.name for item in light_clips()]
    assert "Снимает всё" in [item.name for item in hard_clips()]
    assert "В кресле" in [item.name for item in hard_clips()]
    for item in light_clips():
        assert allowed(item.prompt)
        assert ref_file(item) is None
    for item in hard_clips():
        assert item.locked
        assert "без одежды" in item.prompt
    assert get_clip("nope") is None


async def test_video_catalog_shows_light_and_hard():
    target, state = _FakeTarget(), _FakeState({"mode": "video"}, GenStates.section)
    await generate_mod._show_clips(target, state)
    assert len(target.answers) == 1
    assert target.answers[0][0] == texts.CHOOSE_CLIPS
    cbs = _callbacks(target.answers[0][1])
    assert cbs.index("clip:dance") < cbs.index("nav:noop", 1) < cbs.index("clip:undress")
    assert "clip:walk" in cbs and "clip:chair" in cbs
    assert "shop:subs" not in cbs
    rows = target.answers[0][1].inline_keyboard
    headers = [row[0].text for row in rows if len(row) == 1 and row[0].callback_data == "nav:noop"]
    assert headers == [texts.CLIP_SECTION_LIGHT, texts.CLIP_SECTION_HARD]


async def test_hard_clip_without_subscription_opens_paywall(session_factory):
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 97, "u")
        user.crystals = 10
        user.sub_until = None
        await s.commit()
        state = _FakeState({"people": [], "mode": "video"}, GenStates.scene)
        message = _CapMessage()
        cb = _FakeCb("clip:bed", message)
        settings = Settings(_env_file=None, bot_token="x", admin_ids=[])
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=1, image_bytes=b"IMG", cost_usd=0, error=None)
        )
        await generate_mod.clip_chosen(cb, state, s, user, settings, generator)
    assert generator.calls == []
    assert "подписк" in message.answers[-1][0].lower()
    assert any(item.startswith("buy:sub_") for item in _callbacks(message.answers[-1][1]))


async def test_light_clip_asks_for_the_girl_photo(session_factory):
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 98, "u")
        user.crystals = 10
        await s.commit()
        state = _FakeState({"people": [], "mode": "video"}, GenStates.scene)
        message = _CapMessage()
        cb = _FakeCb("clip:dance", message)
        settings = Settings(_env_file=None, bot_token="x", admin_ids=[])
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=1, image_bytes=b"IMG", cost_usd=0, error=None)
        )
        await generate_mod.clip_chosen(cb, state, s, user, settings, generator)
    assert generator.calls == []
    assert message.answers[-1][0] == texts.SEND_PERSON_VIDEO
    assert state._data["clip_id"] == "dance"
    assert state._state == GenStates.person1
