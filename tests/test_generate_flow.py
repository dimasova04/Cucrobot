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


def _actor_ids(cbs):
    return [c for c in cbs if c.startswith("act:") and ":page:" not in c and c != "act:hero"]


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
        assert len(_actor_ids(first)) == 10
        assert "act:hero" in first  # кнопка «Свой герой»
        assert "nav:back:photo" in first  # шаг назад — к загрузке фото
        assert "act:page:1" in first and "act:page:-1" not in first

        target2 = _FakeTarget()
        await _show_actors(target2, state, s, page=1)
        second = _callbacks(target2.answers[0][1])
        assert "act:page:0" in second and "act:page:2" in second

        target3 = _FakeTarget()
        await _show_actors(target3, state, s, page=2)
        third = _callbacks(target3.answers[0][1])
        assert len(_actor_ids(third)) == 3
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
        # сессия не собрана — «Назад» ведёт к списку актёров
        assert "nav:back:actors" in cbs


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
        self.caption = None
        self.documents = []
        self.photo = None
        self.document = None
        self.bot = SimpleNamespace()

    async def answer(self, text, reply_markup=None, **kw):
        self.answers.append((text, reply_markup))
        return _FakeSentMessage()

    async def answer_photo(self, *a, **kw):
        self.photo_sent = True
        self.caption = kw.get("caption")
        return _FakeSentMessage(photo=[SimpleNamespace(file_id="fid")])

    async def answer_document(self, document, **kw):
        self.documents.append(document)
        return _FakeSentMessage()


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
        # id генерации сохранён для кнопки «Скачать в HD»
        assert state._data["last_generation_id"] == 999


class _FakeBot:
    def __init__(self, data=b"IMG"):
        self._data = data

    async def download(self, file_id):
        import io

        return io.BytesIO(self._data)


async def test_hero_photo_starts_generation_without_catalog_actor(session_factory, monkeypatch):
    monkeypatch.setattr(generate_mod.faces, "has_face", lambda data: True)
    async with session_factory() as s:
        await catalog.create_actor(s, "Стэйтем", "desc", ["f1", "f2"], None)
        await catalog.create_scene(s, "Яхта", "on a yacht", "portrait", None, None)
        user = await repo.get_or_create_user(s, 77, "u")
        user.crystals = 10
        await s.commit()

        state = _FakeState(
            data={"people": ["p1"], "actors": [], "hero_file_id": None, "scene_id": None,
                  "custom_text": None, "custom_file_id": None, "detail": None},
            state=GenStates.hero,
        )
        message = _FakeCbMessage()
        message.photo = [SimpleNamespace(file_id="hero_fid")]
        message.document = None
        settings = Settings(_env_file=None, bot_token="x")
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=5, image_bytes=b"IMG", cost_usd=0.1, error=None)
        )
        await generate_mod.got_hero_photo(message, state, s, _FakeBot(), user, settings, generator)

    req = generator.calls[0]
    assert req.hero_file_id == "hero_fid" and req.actor_ids == []
    assert req.scene_id is not None
    assert state._data["hero_file_id"] == "hero_fid"
    assert message.photo_sent is True
    # подпись под результатом называет «своего героя»
    assert texts.HERO_LABEL in message.caption


async def test_act_hero_button_asks_for_photo():
    state = _FakeState(data={"people": ["p1"], "actors": [], "_pick_mode": "change"}, state=GenStates.actor1)
    message = _FakeCbMessage()
    cb = _FakeCb("act:hero", message)
    await generate_mod.act_hero(cb, state)
    text, markup = message.answers[0]
    assert text == texts.SEND_HERO
    assert "_pick_mode" not in state._data
    assert state._state == GenStates.hero
    assert _callbacks(markup) == ["nav:back:actors", "gen:cancel"]


class _FakeUser:
    def __init__(self, uid):
        self.id = uid


async def test_hd_button_sends_document(session_factory, monkeypatch):
    from database.models import Generation

    async with session_factory() as s:
        await repo.get_or_create_user(s, 21, "u")
        gen = Generation(user_id=21, model_air="m", model_tier="base", actors=[], location="x",
                         crystals_charged=1, status="done", result_url="http://x/orig.jpg")
        s.add(gen)
        await s.commit()
        gid = gen.id

        async def fake_download(url):
            assert url == "http://x/orig.jpg"
            return b"BIGIMG"

        monkeypatch.setattr(generate_mod.gen_service, "download_bytes", fake_download)
        message = _FakeCbMessage()
        cb = _FakeCb(f"gen:hd:{gid}", message)
        await generate_mod.gen_hd(cb, s, _FakeUser(21))

    assert message.documents and message.documents[0].filename == "photo_hd.jpg"
    assert message.documents[0].data == b"BIGIMG"


async def test_hd_button_reports_expired_link(session_factory, monkeypatch):
    from database.models import Generation

    async with session_factory() as s:
        await repo.get_or_create_user(s, 22, "u")
        gen = Generation(user_id=22, model_air="m", model_tier="base", actors=[], location="x",
                         crystals_charged=1, status="done", result_url="http://x/gone.jpg")
        s.add(gen)
        await s.commit()
        gid = gen.id

        async def boom(url):
            raise RuntimeError("404")

        monkeypatch.setattr(generate_mod.gen_service, "download_bytes", boom)
        message = _FakeCbMessage()
        cb = _FakeCb(f"gen:hd:{gid}", message)
        await generate_mod.gen_hd(cb, s, _FakeUser(22))

    assert not message.documents
    assert message.answers[-1][0] == texts.HD_EXPIRED


async def test_hd_button_rejects_foreign_generation(session_factory):
    from database.models import Generation

    async with session_factory() as s:
        await repo.get_or_create_user(s, 23, "u")
        gen = Generation(user_id=23, model_air="m", model_tier="base", actors=[], location="x",
                         crystals_charged=1, status="done", result_url="http://x/orig.jpg")
        s.add(gen)
        await s.commit()
        message = _FakeCbMessage()
        cb = _FakeCb(f"gen:hd:{gen.id}", message)
        await generate_mod.gen_hd(cb, s, _FakeUser(999))

    assert cb.answered == [(texts.HD_EXPIRED, True)]
    assert not message.documents
