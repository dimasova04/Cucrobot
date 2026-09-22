from types import SimpleNamespace

from bot import texts
from bot.flow import GenStates
from bot.handlers import generate as generate_mod
from bot.handlers.generate import _show_actors, _show_scenes
from config.settings import Settings
from database import repo
from services import catalog
from services.generation.generator import GenerationOutcome


class _FakeTarget:
    def __init__(self):
        self.answers = []

    async def answer(self, text, reply_markup=None, **kw):
        self.answers.append((text, reply_markup))
        return SimpleNamespace(photo=None)


class _FakeState:
    def __init__(self, data=None, state=None):
        self._data = data or {}
        self._state = state
        self.cleared = False

    async def get_data(self):
        return dict(self._data)

    async def set_data(self, d):
        self._data = d

    async def set_state(self, st):
        self._state = st

    async def get_state(self):
        return self._state

    async def clear(self):
        self.cleared = True
        self._data, self._state = {}, None


def _callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


async def test_show_actors_on_empty_catalog(session_factory):
    async with session_factory() as s:
        target, state = _FakeTarget(), _FakeState()
        await _show_actors(target, state, s)
    text, markup = target.answers[0]
    assert text == texts.CATALOG_EMPTY
    assert state.cleared is True
    assert markup.keyboard[0][0].text == texts.BTN_CREATE  # главное меню


async def test_show_actors_pages_by_ten(session_factory):
    async with session_factory() as s:
        for i in range(23):
            await catalog.create_actor(s, f"A{i:02d}", "desc", ["f1", "f2"], 1)
        await s.commit()
    async with session_factory() as s:
        target, state = _FakeTarget(), _FakeState()
        await _show_actors(target, state, s)
        first = _callbacks(target.answers[0][1])
        assert len([c for c in first if c.startswith("act:") and ":page:" not in c and c != "act:addperson"]) == 10
        assert "act:addperson" in first  # один человек загружен — кнопка «добавить человека» есть
        assert "act:page:1" in first and "act:page:-1" not in first

        target2 = _FakeTarget()
        await _show_actors(target2, state, s, page=1)
        second = _callbacks(target2.answers[0][1])
        assert "act:page:0" in second and "act:page:2" in second

        target3 = _FakeTarget()
        await _show_actors(target3, state, s, page=2)
        third = _callbacks(target3.answers[0][1])
        assert len([c for c in third if c.startswith("act:") and ":page:" not in c and c != "act:addperson"]) == 3
        assert "act:page:1" in third and "act:page:3" not in third
        assert state._state == GenStates.actor1


async def test_show_scenes_pages_by_twelve(session_factory):
    async with session_factory() as s:
        for i in range(12):
            await catalog.create_scene(s, f"Сцена {i}", f"prompt {i}", "portrait", None, None)
        await s.commit()
    async with session_factory() as s:
        scenes = await catalog.list_scenes(s)
        assert len(scenes) == 12
        target, state = _FakeTarget(), _FakeState()
        await _show_scenes(target, state, s)
        cbs = _callbacks(target.answers[0][1])
        # ровно одна страница: стрелок нет, «Своя сцена» на месте
        assert not [c for c in cbs if ":page:" in c]
        assert "scene:custom" in cbs


class _FakeGenerator:
    def __init__(self, outcome):
        self.calls = []
        self._outcome = outcome

    async def run(self, req):
        self.calls.append(req)
        return self._outcome


class _FakeSentMessage:
    def __init__(self, photo=None):
        self.photo = photo
        self.edited = []
        self.deleted = False

    async def edit_text(self, text, **kw):
        self.edited.append(text)

    async def delete(self):
        self.deleted = True


class _FakeCbMessage:
    """Заглушка под cb.message: копит ответы, умеет answer/answer_photo."""

    def __init__(self):
        self.answers = []
        self.photo_sent = False
        self.bot = SimpleNamespace()

    async def answer(self, text, reply_markup=None, **kw):
        self.answers.append((text, reply_markup))
        return _FakeSentMessage()

    async def answer_photo(self, *a, **kw):
        self.photo_sent = True
        return _FakeSentMessage(photo=[SimpleNamespace(file_id="fid")])


class _FakeCb:
    def __init__(self, data, message):
        self.data = data
        self.message = message
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


async def test_actor1_tap_triggers_generation_failed(session_factory):
    async with session_factory() as s:
        actor = await catalog.create_actor(s, "Стэйтем", "desc", ["f1", "f2"], None)
        await catalog.create_scene(s, "Яхта", "on a yacht", "portrait", None, None)
        user = await repo.get_or_create_user(s, 42, "u")
        user.crystals = 10
        await s.commit()

        state = _FakeState(data={"people": ["p1"], "actors": [], "scene_id": None, "custom_text": None, "custom_file_id": None, "detail": None}, state=GenStates.actor1)
        message = _FakeCbMessage()
        cb = _FakeCb(f"act:{actor.id}", message)
        settings = Settings(_env_file=None, bot_token="x")
        generator = _FakeGenerator(GenerationOutcome(status="failed", generation_id=1, image_bytes=None, cost_usd=None, error="boom"))

        await generate_mod.actor1_chosen(cb, state, s, user, settings, generator)

        assert len(generator.calls) == 1
        req = generator.calls[0]
        assert req.actor_ids == [actor.id]
        scenes = await catalog.list_scenes(s)
        assert req.scene_id in [sc.id for sc in scenes]
        assert cb.answered == [(None, False)]
        assert state._state == GenStates.result
        assert not message.photo_sent  # failed: без отправки фото
        assert message.answers[-1][0] == texts.GENERATING


async def test_actor1_tap_triggers_generation_done(session_factory):
    async with session_factory() as s:
        actor = await catalog.create_actor(s, "Стэйтем", "desc", ["f1", "f2"], None)
        await catalog.create_scene(s, "Яхта", "on a yacht", "portrait", None, None)
        user = await repo.get_or_create_user(s, 43, "u")
        user.crystals = 10
        await s.commit()

        state = _FakeState(data={"people": ["p1"], "actors": [], "scene_id": None, "custom_text": None, "custom_file_id": None, "detail": None}, state=GenStates.actor1)
        message = _FakeCbMessage()
        cb = _FakeCb(f"act:{actor.id}", message)
        settings = Settings(_env_file=None, bot_token="x")
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=999, image_bytes=b"IMG", cost_usd=0.1, error=None)
        )

        await generate_mod.actor1_chosen(cb, state, s, user, settings, generator)

        assert len(generator.calls) == 1
        assert message.photo_sent is True
        assert state._state == GenStates.result
