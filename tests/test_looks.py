from datetime import timedelta

from bot import texts
from bot.flow import GenStates, apply_catalog_scene, apply_look, empty_data
from bot.handlers import generate as generate_mod
from bot.looks import LOOKS, free_looks, get_look, locked_looks
from config.settings import Settings
from database import repo
from database.base import utcnow
from services.generation.content_filter import is_allowed
from services.generation.generator import GenerationOutcome
from services.generation.prompt_builder import GenerationInput, build
from tests.test_generate_flow import _CapMessage, _FakeCb, _FakeGenerator, _FakeState, _FakeTarget, _callbacks


def test_classic_buttons_split_into_an_open_block_and_a_locked_block():
    ids = [item.id for item in LOOKS]
    assert len(ids) == len(set(ids))
    free_names = [item.name for item in free_looks()]
    locked_names = [item.name for item in locked_looks()]
    assert "В бикини" in free_names
    assert "В мини-юбке" in free_names
    assert "В обтягивающих шортах" in free_names
    assert "Полностью без всего" in locked_names
    assert "Ню на кровати" in locked_names
    assert "В кресле с раздвинутыми ногами" in locked_names
    for item in free_looks():
        assert item.prompt.startswith("[solo]")
        assert is_allowed(item.prompt)
        assert len(f"look:{item.id}".encode()) <= 64
        assert len(item.name) <= 64
    for item in locked_looks():
        assert item.locked
        assert item.prompt.startswith("[solo]")
        assert "без одежды" in item.prompt
        assert len(item.name) <= 64


def test_locked_look_stays_one_adult_woman():
    look = get_look("chair")
    prompt, refs = build(
        GenerationInput(
            people=["p"], actors=[], scene_prompt=look.prompt, scene_ref=None,
            detail=None, width=832, height=1248,
        ),
        max_refs=4,
    )
    assert refs == ["p"]
    assert "Exactly 1 person in the frame" in prompt
    assert "кресле" in prompt


def test_catalog_scene_clears_the_look():
    data = empty_data()
    data["people"] = ["p"]
    apply_look(data, "bed", get_look("bed").prompt)
    assert data["look_id"] == "bed"
    apply_catalog_scene(data, 3)
    assert "look_id" not in data
    assert data["scene_id"] == 3
    assert data["custom_text"] is None


async def test_both_look_blocks_are_visible(session_factory):
    target, state = _FakeTarget(), _FakeState({"people": ["p"]}, GenStates.section)
    await generate_mod._show_looks(target, state)
    assert target.answers[0][0] == texts.CHOOSE_LOOKS_FREE
    free_cbs = _callbacks(target.answers[0][1])
    sub_cbs = _callbacks(target.answers[1][1])
    assert "look:bikini" in free_cbs and "look:shorts" in free_cbs
    assert "look:nude" in sub_cbs and "look:bed" in sub_cbs and "look:chair" in sub_cbs
    assert "look:places" in sub_cbs
    assert "shop:subs" not in free_cbs and "shop:subs" not in sub_cbs
    assert state._state == GenStates.scene


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
        cb = _FakeCb("look:bed", message)
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
        cb = _FakeCb("look:nude", message)
        settings = Settings(_env_file=None, bot_token="x", admin_ids=[95], cost_base=1, cost_premium=3)
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=4, image_bytes=b"IMG", cost_usd=0.04, error=None, seed=1)
        )
        monkeypatch.setattr("bot.handlers.generate.watermark.apply_free_mark", lambda data: data)
        await generate_mod.look_chosen(cb, state, s, user, settings, generator)
    assert generator.calls[0].custom_scene_text.startswith("[solo]")
    assert "без одежды" in generator.calls[0].custom_scene_text
    assert message.photos == [texts.PHOTO_SCENE_CAPTION.format(scene="Полностью без всего")]


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
        cb = _FakeCb("look:chair", message)
        settings = Settings(_env_file=None, bot_token="x", admin_ids=[], cost_base=1, cost_premium=3)
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=5, image_bytes=b"IMG", cost_usd=0.04, error=None, seed=1)
        )
        await generate_mod.look_chosen(cb, state, s, user, settings, generator)
    assert "кресле" in generator.calls[0].custom_scene_text
    assert state._data["look_id"] == "chair"
