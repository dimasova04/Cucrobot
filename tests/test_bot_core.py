from types import SimpleNamespace

from bot import keyboards, texts
from bot.middlewares import needs_rules
from database.models import User


def _msg(text):
    return SimpleNamespace(text=text, data=None)


def _cb(data):
    return SimpleNamespace(text=None, data=data)


def test_needs_rules():
    u = User(id=1)
    assert needs_rules(u, _msg("привет"))
    assert not needs_rules(u, _msg("/start"))
    assert not needs_rules(u, _msg("/start ref123"))
    assert not needs_rules(u, _cb("rules:accept"))
    assert needs_rules(u, _cb("shop:open"))
    u.rules_accepted_at = __import__("datetime").datetime(2026, 1, 1)
    assert not needs_rules(u, _msg("привет"))


def test_grid_layout_and_extra_rows():
    kb = keyboards.grid([("A", "a"), ("B", "b"), ("C", "c")], cols=2, extra_rows=[[("Назад", "back")]])
    rows = kb.inline_keyboard
    assert [len(r) for r in rows] == [2, 1, 1]
    assert rows[0][0].text == "A" and rows[0][0].callback_data == "a"
    assert rows[2][0].callback_data == "back"


def test_main_menu_has_five_buttons():
    kb = keyboards.main_menu()
    btn_texts = [b.text for row in kb.keyboard for b in row]
    assert len(btn_texts) == 5 and "📸 Создать фото" in btn_texts


def test_cancel_row():
    assert keyboards.cancel_row() == [(texts.BTN_CANCEL, "gen:cancel")]


class _PhotoTarget:
    """answer_photo падает первые `fails` раз."""

    def __init__(self, fails: int):
        self.fails = fails
        self.calls = 0

    async def answer_photo(self, *a, **kw):
        self.calls += 1
        if self.calls <= self.fails:
            raise RuntimeError("telegram is down")
        return SimpleNamespace(photo=[SimpleNamespace(file_id="fid")])


async def test_send_result_photo_retries_once(monkeypatch):
    from bot.handlers import generate

    slept = []

    async def fake_sleep(sec):
        slept.append(sec)

    monkeypatch.setattr(generate.asyncio, "sleep", fake_sleep)
    target = _PhotoTarget(fails=1)
    sent = await generate.send_result_photo(target, b"IMG", "caption")
    assert sent is not None and target.calls == 2 and slept == [1]


async def test_send_result_photo_gives_up_after_two_attempts(monkeypatch):
    from bot.handlers import generate

    async def fake_sleep(sec):
        pass

    monkeypatch.setattr(generate.asyncio, "sleep", fake_sleep)
    target = _PhotoTarget(fails=5)
    assert await generate.send_result_photo(target, b"IMG", "caption") is None
    assert target.calls == 2


async def test_error_handler_answers_callback():
    from aiogram.types import ErrorEvent

    from main import on_unhandled_error

    answered = []

    async def answer(text, **kw):
        answered.append(text)

    cb = SimpleNamespace(from_user=SimpleNamespace(id=1), answer=answer)
    event = ErrorEvent.model_construct(
        update=SimpleNamespace(callback_query=cb, message=None), exception=RuntimeError("boom")
    )
    assert await on_unhandled_error(event) is True
    assert answered == [texts.GENERIC_ERROR]


async def test_error_handler_swallows_send_failure():
    from aiogram.types import ErrorEvent

    from main import on_unhandled_error

    async def boom(*a, **kw):
        raise RuntimeError("cannot send")

    msg = SimpleNamespace(from_user=SimpleNamespace(id=1), answer=boom)
    event = ErrorEvent.model_construct(
        update=SimpleNamespace(callback_query=None, message=msg), exception=RuntimeError("boom")
    )
    assert await on_unhandled_error(event) is True
