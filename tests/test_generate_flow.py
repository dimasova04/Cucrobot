from types import SimpleNamespace

from bot import texts
from bot.flow import GenStates
from bot.handlers.generate import _show_actors, _show_scenes
from services import catalog


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
        assert len([c for c in first if c.startswith("act:") and ":page:" not in c]) == 10
        assert "act:page:1" in first and "act:page:-1" not in first

        target2 = _FakeTarget()
        await _show_actors(target2, state, s, page=1)
        second = _callbacks(target2.answers[0][1])
        assert "act:page:0" in second and "act:page:2" in second

        target3 = _FakeTarget()
        await _show_actors(target3, state, s, page=2)
        third = _callbacks(target3.answers[0][1])
        assert len([c for c in third if c.startswith("act:") and ":page:" not in c]) == 3
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
