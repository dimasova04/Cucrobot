from types import SimpleNamespace

from bot import keyboards, texts
from bot.middlewares import needs_rules
from database.models import User


def _msg(text):
    return SimpleNamespace(text=text, data=None, successful_payment=None)


def _cb(data):
    return SimpleNamespace(text=None, data=data, successful_payment=None)


def test_needs_rules():
    u = User(id=1)
    assert needs_rules(u, _msg("привет"))
    assert not needs_rules(u, _msg("/start"))
    assert not needs_rules(u, _msg("/start ref123"))
    assert not needs_rules(u, _cb("rules:accept"))
    assert needs_rules(u, _cb("shop:open"))
    # оплата проходит даже без принятых правил: деньги уже списаны
    assert not needs_rules(u, SimpleNamespace(text=None, data=None, successful_payment=object()))
    u.rules_accepted_at = __import__("datetime").datetime(2026, 1, 1)
    assert not needs_rules(u, _msg("привет"))


def test_grid_layout_and_extra_rows():
    kb = keyboards.grid([("A", "a"), ("B", "b"), ("C", "c")], cols=2, extra_rows=[[("Назад", "back")]])
    rows = kb.inline_keyboard
    assert [len(r) for r in rows] == [2, 1, 1]
    assert rows[0][0].text == "A" and rows[0][0].callback_data == "a"
    assert rows[2][0].callback_data == "back"


def test_main_menu_has_three_buttons():
    kb = keyboards.main_menu()
    btn_texts = [b.text for row in kb.keyboard for b in row]
    assert len(btn_texts) == 3 and texts.BTN_PROFILE in btn_texts


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
    sent = await generate.send_result_photo(target, b"IMG", "caption", {"people": ["a"], "actors": [1]})
    assert sent is not None and target.calls == 2 and slept == [1]


async def test_send_result_photo_gives_up_after_two_attempts(monkeypatch):
    from bot.handlers import generate

    async def fake_sleep(sec):
        pass

    monkeypatch.setattr(generate.asyncio, "sleep", fake_sleep)
    target = _PhotoTarget(fails=5)
    assert await generate.send_result_photo(target, b"IMG", "caption", {"people": ["a"], "actors": [1]}) is None
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


async def test_rules_gate_lets_successful_payment_through_for_blocked_user():
    from bot.middlewares import RulesGateMiddleware

    handled = []

    async def handler(event, data):
        handled.append(event)
        return "ok"

    user = User(id=1, is_blocked=True)
    payment = SimpleNamespace(text=None, data=None, successful_payment=object())
    assert await RulesGateMiddleware()(handler, payment, {"user": user}) == "ok"
    assert handled == [payment]
    # обычное сообщение заблокированного пользователя по-прежнему отбрасывается
    assert await RulesGateMiddleware()(handler, _msg("привет"), {"user": user}) is None
    assert len(handled) == 1


class _AdminMessage:
    def __init__(self, admin_id=607396740):
        self.from_user = SimpleNamespace(id=admin_id)
        self.answers = []

    async def answer(self, text, **kw):
        self.answers.append(text)


async def test_admin_block_and_unblock(session_factory):
    from aiogram.filters import CommandObject

    from bot.handlers.admin.stats import cmd_block, cmd_unblock
    from database import repo

    async with session_factory() as s:
        await repo.get_or_create_user(s, 5, "u")
        await s.commit()

    async with session_factory() as s:
        msg = _AdminMessage()
        await cmd_block(msg, CommandObject(args="5"), s)
        await s.commit()
        assert msg.answers == [texts.ADM_BLOCK_OK.format(uid=5)]
    async with session_factory() as s:
        assert (await repo.get_user(s, 5)).is_blocked is True

    async with session_factory() as s:
        msg = _AdminMessage()
        await cmd_unblock(msg, CommandObject(args="5"), s)
        await s.commit()
        assert msg.answers == [texts.ADM_UNBLOCK_OK.format(uid=5)]
    async with session_factory() as s:
        assert (await repo.get_user(s, 5)).is_blocked is False

    async with session_factory() as s:
        msg = _AdminMessage()
        await cmd_block(msg, CommandObject(args="not-a-number"), s)
        assert msg.answers == [texts.ADM_USAGE_BLOCK]
        msg = _AdminMessage()
        await cmd_block(msg, CommandObject(args="98765"), s)
        assert msg.answers == [texts.ADM_USER_NOT_FOUND]


async def test_admin_give_cannot_go_below_zero(session_factory):
    from aiogram.filters import CommandObject

    from bot.handlers.admin.stats import cmd_give
    from database import repo

    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 5, "u")
        user.crystals = 2
        await s.commit()
    async with session_factory() as s:
        msg = _AdminMessage()
        await cmd_give(msg, CommandObject(args="5 -10"), s)
        assert msg.answers == [texts.ADM_GIVE_INSUFFICIENT.format(balance=2)]
    async with session_factory() as s:
        assert (await repo.get_user(s, 5)).crystals == 2


async def _feed_cancel_update(monkeypatch, dp, session_factory, user_id: int, admin_state=None):
    """Прогоняет текстовое /cancel через реальный (общий на всю сессию, см.
    фикстуру `dispatcher`) Dispatcher — так же, как это делает aiogram при
    получении апдейта от Telegram."""
    from datetime import datetime

    from aiogram import Bot
    from aiogram.types import Chat, Message, MessageEntity, Update
    from aiogram.types import User as TgUser

    from database import repo

    bot = Bot(token="42:TEST")

    async with session_factory() as s:
        user = await repo.get_or_create_user(s, user_id, "u")
        user.rules_accepted_at = datetime.now()
        await s.commit()

    if admin_state is not None:
        await dp.fsm.get_context(bot, chat_id=user_id, user_id=user_id).set_state(admin_state)

    answers: list[str] = []

    async def fake_answer(self, text=None, **kwargs):
        answers.append(text)
        return None

    monkeypatch.setattr(Message, "answer", fake_answer)

    update = Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=datetime.now(),
            chat=Chat(id=user_id, type="private"),
            from_user=TgUser(id=user_id, is_bot=False, first_name="u"),
            text="/cancel",
            entities=[MessageEntity(type="bot_command", offset=0, length=7)],
        ),
    )
    await dp.feed_update(bot, update)
    await bot.session.close()
    return answers


async def test_cancel_reaches_regular_user(dispatcher, dispatcher_session_factory, monkeypatch):
    # Регрессия: AdminOnlyMiddleware не должна перехватывать /cancel обычного
    # пользователя — cmd_cancel в admin/actors.py и admin/scenes.py ограничен
    # состояниями своего диалога, и до menu_router.cmd_cancel доходит только
    # не-админский вызов.
    answers = await _feed_cancel_update(monkeypatch, dispatcher, dispatcher_session_factory, user_id=555)
    assert texts.CANCELLED in answers
    assert texts.ADMIN_ONLY not in answers


async def test_cancel_reaches_admin_inside_actor_dialog(dispatcher, dispatcher_session_factory, monkeypatch):
    from bot.handlers.admin.actors import AdminActorStates

    answers = await _feed_cancel_update(
        monkeypatch, dispatcher, dispatcher_session_factory, user_id=607396740, admin_state=AdminActorStates.name
    )
    assert texts.CANCELLED in answers
    assert texts.ADMIN_ONLY not in answers


def test_admin_help_lists_every_admin_command():
    import re
    from bot.handlers.admin.stats import cmd_admin_help  # noqa: F401  (handler exists)

    listed = set(re.findall(r"/(\w+)", texts.ADM_HELP))
    for cmd in ("admin", "stats", "user", "give", "sub", "block", "unblock", "actors", "scenes", "cancel"):
        assert cmd in listed
