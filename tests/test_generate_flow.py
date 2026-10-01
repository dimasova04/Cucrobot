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
    return [c for c in cbs if c.startswith("act:") and c.removeprefix("act:").isdigit()]


async def test_show_actors_on_empty_catalog_still_offers_a_typed_name(session_factory):
    async with session_factory() as s:
        target, state = _FakeTarget(), _FakeState()
        await _show_actors(target, state, s)
    text, markup = target.answers[0]
    assert text == texts.CHOOSE_ACTOR
    assert "act:write" in _callbacks(markup)
    assert state.cleared is False


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
        assert "act:write" in first  # «Написать своё»
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

        assert generator.calls == []
        assert state._data["actors"] == [actor.id]
        assert state._state == GenStates.scene
        assert message.answers[-1][0] == texts.CHOOSE_SCENE


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

        assert generator.calls == []
        assert state._state == GenStates.scene
        assert state._data["actors"] == [actor.id]


class _FakeBot:
    def __init__(self, data=b"IMG"):
        self._data = data

    async def download(self, file_id):
        import io

        return io.BytesIO(self._data)


async def test_typed_name_skip_goes_to_scenes(session_factory):
    async with session_factory() as s:
        await catalog.create_scene(s, "Яхта", "on a yacht", "portrait", None, None)
        user = await repo.get_or_create_user(s, 77, "u")
        user.crystals = 10
        await s.commit()

        state = _FakeState(
            data={"people": ["p1"], "actors": [], "named": [], "pending_name": "Рокко", "pending_files": [],
                  "scene_id": None, "custom_text": None, "custom_file_id": None, "detail": None},
            state=GenStates.actor_photos,
        )
        message = _FakeCbMessage()
        cb = _FakeCb("act:photos:skip", message)
        settings = Settings(_env_file=None, bot_token="x")
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=5, image_bytes=b"IMG", cost_usd=0.1, error=None)
        )
        await generate_mod.actor_photos_skip(cb, state, s, user, settings, generator)

    assert generator.calls == []
    assert state._data["named"] == [{"name": "Рокко", "files": []}]
    assert state._state == GenStates.scene
    assert message.answers[-1][0] == texts.CHOOSE_SCENE


async def test_write_own_asks_for_a_name():
    state = _FakeState(data={"people": ["p1"], "actors": []}, state=GenStates.actor1)
    message = _FakeCbMessage()
    cb = _FakeCb("act:write", message)
    await generate_mod.act_write(cb, state)
    text, markup = message.answers[0]
    assert text == texts.ASK_ACTOR_NAME
    assert state._state == GenStates.actor_name
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


async def test_detail_button_marks_edit_of_previous_result():
    state = _FakeState(
        data={"people": ["p1"], "actors": [1], "named": [], "scene_id": 3,
              "last_generation_id": 77},
        state=GenStates.result,
    )
    message = _FakeCbMessage()
    cb = _FakeCb("gen:detail", message)
    await generate_mod.gen_ask_detail(cb, state)
    assert state._data["edit_mode"] is True
    assert state._data["edit_base_id"] == 77
    assert state._state == GenStates.detail
    assert message.answers[0][0] == texts.ASK_DETAIL


async def test_detail_text_sends_additive_edit_request(session_factory):
    async with session_factory() as s:
        actor = await catalog.create_actor(s, "Стэйтем", "desc", ["f1", "f2"], None)
        scene = await catalog.create_scene(s, "Яхта", "on a yacht", "portrait", None, None)
        user = await repo.get_or_create_user(s, 61, "u")
        user.crystals = 10
        await s.commit()

        state = _FakeState(
            data={"people": ["p1"], "actors": [actor.id], "named": [],
                  "scene_id": scene.id, "custom_text": None, "custom_file_id": None,
                  "detail": None, "last_generation_id": 77,
                  "edit_mode": True, "edit_base_id": 77},
            state=GenStates.detail,
        )
        message = _FakeCbMessage()
        message.text = "в пальто"
        settings = Settings(_env_file=None, bot_token="x")
        generator = _FakeGenerator(
            GenerationOutcome(status="done", generation_id=78, image_bytes=b"IMG",
                              cost_usd=0.1, error=None, seed=99)
        )
        await generate_mod.detail_text(message, state, s, user, settings, generator)

    req = generator.calls[0]
    assert req.edit_mode is True and req.base_generation_id == 77 and req.detail == "в пальто"
    # флаги правки одноразовые: следующий запуск — обычная генерация
    assert "edit_mode" not in state._data and "edit_base_id" not in state._data
    assert state._data["last_generation_id"] == 78 and state._data["last_seed"] == 99


async def test_new_photoshoot_is_not_an_edit(session_factory):
    async with session_factory() as s:
        actor = await catalog.create_actor(s, "Стэйтем", "desc", ["f1", "f2"], None)
        scene = await catalog.create_scene(s, "Яхта", "on a yacht", "portrait", None, None)
        user = await repo.get_or_create_user(s, 62, "u")
        user.crystals = 10
        await s.commit()

        state = _FakeState(
            data={"people": ["p1"], "actors": [actor.id], "named": [],
                  "scene_id": scene.id, "custom_text": None, "custom_file_id": None,
                  "detail": "в пальто", "last_generation_id": 77, "last_seed": 42,
                  "edit_mode": True, "edit_base_id": 77},
            state=GenStates.result,
        )
        message = _FakeCbMessage()
        cb = _FakeCb("gen:more", message)
        settings = Settings(_env_file=None, bot_token="x")
        generator = _FakeGenerator(
            GenerationOutcome(status="failed", generation_id=79, image_bytes=None,
                              cost_usd=None, error="boom")
        )
        await generate_mod.gen_more(cb, state, s, user, settings, generator)

    req = generator.calls[0]
    assert req.edit_mode is False and req.base_generation_id is None
    assert state._data["last_seed"] is None


async def test_change_scene_drops_the_edit_flags(session_factory):
    async with session_factory() as s:
        await catalog.create_actor(s, "Стэйтем", "desc", ["f1", "f2"], None)
        await catalog.create_scene(s, "Яхта", "on a yacht", "portrait", None, None)
        await s.commit()
        data = {"people": ["p1"], "actors": [1], "named": [], "scene_id": 1,
                "custom_text": None, "custom_file_id": None, "detail": None,
                "edit_mode": True, "edit_base_id": 77}

        state = _FakeState(data=dict(data), state=GenStates.result)
        await generate_mod.gen_change_scene(_FakeCb("gen:change_scene", _FakeCbMessage()), state, s)
        assert "edit_mode" not in state._data and "edit_base_id" not in state._data


def _ready_session(actor_id, scene_id):
    return {
        "people": ["p1"], "actors": [actor_id], "named": [],
        "scene_id": scene_id, "custom_text": None, "custom_file_id": None, "detail": None,
    }


async def test_success_reports_spent_crystal_and_balance(session_factory):
    from database.base import utcnow

    async with session_factory() as s:
        actor = await catalog.create_actor(s, "Стэйтем", "desc", ["f1", "f2"], None)
        scene = await catalog.create_scene(s, "Яхта", "on a yacht", "portrait", None, None)
        user = await repo.get_or_create_user(s, 80, "u")
        user.crystals = 4
        user.last_bonus_at = utcnow()
        await s.commit()
        actor_id, scene_id = actor.id, scene.id

    async with session_factory() as s:
        user = await repo.get_user(s, 80)
        state = _FakeState(data=_ready_session(actor_id, scene_id), state=GenStates.result)
        message = _FakeCbMessage()
        settings = Settings(_env_file=None, bot_token="x")
        await generate_mod._run_generation(
            message, state, s, user, settings,
            _FakeGenerator(GenerationOutcome(status="done", generation_id=3, image_bytes=b"IMG", cost_usd=0.04, error=None)),
        )
    assert message.answers[0][0] == texts.GENERATING
    assert message.answers[1][0] == "-1 кристалл, баланс: 4"
    assert message.answers[1][1] is None
    assert message.photo_sent is True


async def test_zero_balance_after_charge_offers_bonus_or_shop(session_factory):
    from database.base import utcnow

    async with session_factory() as s:
        actor = await catalog.create_actor(s, "Стэйтем", "desc", ["f1", "f2"], None)
        scene = await catalog.create_scene(s, "Яхта", "on a yacht", "portrait", None, None)
        user = await repo.get_or_create_user(s, 81, "u")
        user.crystals = 1
        await s.commit()
        actor_id, scene_id = actor.id, scene.id

    class _Spend:
        async def run(self, req):
            async with session_factory() as db:
                u = await repo.get_user(db, 81)
                u.crystals = 0
                await db.commit()
            return GenerationOutcome(status="done", generation_id=4, image_bytes=b"IMG", cost_usd=0.04, error=None)

    async with session_factory() as s:
        user = await repo.get_user(s, 81)
        message = _FakeCbMessage()
        await generate_mod._run_generation(
            message, _FakeState(data=_ready_session(actor_id, scene_id)), s, user,
            Settings(_env_file=None, bot_token="x"), _Spend(),
        )
    text, markup = message.answers[1]
    assert text == "-1 кристалл, баланс: 0\n\n" + texts.BALANCE_EMPTY_BONUS
    assert _callbacks(markup) == ["bonus:claim"]

    async with session_factory() as s:
        user = await repo.get_user(s, 81)
        user.crystals = 0
        user.last_bonus_at = utcnow()
        await s.commit()
    async with session_factory() as s:
        user = await repo.get_user(s, 81)
        message = _FakeCbMessage()
        await generate_mod._run_generation(
            message, _FakeState(data=_ready_session(actor_id, scene_id)), s, user,
            Settings(_env_file=None, bot_token="x"), _FakeGenerator(
                GenerationOutcome(status="done", generation_id=1, image_bytes=b"IMG", cost_usd=0, error=None)
            ),
        )
    assert texts.GENERATING not in [a[0] for a in message.answers]
    text, markup = message.answers[0]
    assert texts.BALANCE_EMPTY_BUY in text
    assert _callbacks(markup) == ["shop:packs", "shop:subs"]
