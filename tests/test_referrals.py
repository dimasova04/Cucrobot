from datetime import datetime, timedelta

from aiogram.filters import CommandObject

from bot import texts
from database import repo
from database.base import utcnow
from database.models import Generation, Payment
from services import referrals


def test_normalize_code():
    assert referrals.normalize_code("ABC") == "abc"
    assert referrals.normalize_code("  My_Code1 ") == "my_code1"
    assert referrals.normalize_code("ab") is None
    assert referrals.normalize_code("a" * 33) is None
    assert referrals.normalize_code("bad-code") is None
    assert referrals.normalize_code("код123") is None
    assert referrals.normalize_code("") is None


def test_code_from_payload_and_link():
    assert referrals.code_from_payload("ref_abc") == "abc"
    assert referrals.code_from_payload("ref_ABC") == "abc"
    assert referrals.code_from_payload("ref_x") is None  # слишком короткий
    assert referrals.code_from_payload("abc") is None
    assert referrals.code_from_payload(None) is None
    assert referrals.link_for("CucroBot", "abc") == "https://t.me/CucroBot?start=ref_abc"


async def test_create_code_and_duplicate(session_factory):
    async with session_factory() as s:
        rc = await referrals.create_code(s, "Blogger1", "Блогер", 42, 1)
        await s.commit()
    assert rc.code == "blogger1" and rc.title == "Блогер" and rc.partner_user_id == 42 and rc.is_active is True

    async with session_factory() as s:
        try:
            await referrals.create_code(s, "BLOGGER1", "Он же", None, 1)
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate code must raise")
        try:
            await referrals.create_code(s, "no", "Короткий", None, 1)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid code must raise")

    async with session_factory() as s:
        assert [c.code for c in await referrals.list_codes(s)] == ["blogger1"]
        assert [c.code for c in await referrals.codes_for_partner(s, 42)] == ["blogger1"]
        assert await referrals.codes_for_partner(s, 43) == []


async def test_attribute_only_once(session_factory):
    async with session_factory() as s:
        await referrals.create_code(s, "one", "Первый", None, 1)
        await referrals.create_code(s, "two", "Второй", None, 1)
        user = await repo.get_or_create_user(s, 10, "u")
        assert await referrals.attribute(s, user, "one") is True
        assert user.ref_code == "one" and user.ref_attributed_at is not None
        # вторая ссылка не перебивает первую
        assert await referrals.attribute(s, user, "two") is False
        assert user.ref_code == "one"
        await s.commit()
    async with session_factory() as s:
        assert (await repo.get_user(s, 10)).ref_code == "one"


async def test_attribute_rejects_unknown_and_inactive(session_factory):
    async with session_factory() as s:
        await referrals.create_code(s, "off", "Выключенная", None, 1)
        await referrals.set_active(s, "off", False)
        user = await repo.get_or_create_user(s, 11, "u")
        assert await referrals.attribute(s, user, "off") is False
        assert await referrals.attribute(s, user, "nosuch") is False
        assert user.ref_code is None
        # включили обратно — привязка работает
        await referrals.set_active(s, "off", True)
        assert await referrals.attribute(s, user, "off") is True
        assert await referrals.set_active(s, "nosuch", True) is None


async def _seed_three_users(s):
    now = utcnow()
    await referrals.create_code(s, "part", "Партнёр", 99, 1)
    # 1: принял правила, заплатил 199 Stars и сделал одну генерацию
    u1 = await repo.get_or_create_user(s, 1, "a")
    u1.rules_accepted_at = now
    await referrals.attribute(s, u1, "part")
    s.add(Payment(provider="stars", external_id="c1", user_id=1, product="pack_50", amount=199, currency="XTR"))
    s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x", status="done"))
    s.add(Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x", status="failed"))
    # 2: только принял правила
    u2 = await repo.get_or_create_user(s, 2, "b")
    u2.rules_accepted_at = now
    await referrals.attribute(s, u2, "part")
    # 3: правила не принял
    u3 = await repo.get_or_create_user(s, 3, "c")
    await referrals.attribute(s, u3, "part")
    # 4: пришёл сам, в статистику партнёра не попадает
    await repo.get_or_create_user(s, 4, "d")
    s.add(Payment(provider="tribute", external_id="t4", user_id=4, product="sub_month", amount=49900, currency="rub"))
    s.add(Generation(user_id=4, model_air="m", model_tier="base", actors=[], location="x", status="done"))


async def test_stats_for(session_factory):
    async with session_factory() as s:
        await _seed_three_users(s)
        await s.commit()
    async with session_factory() as s:
        st = await referrals.stats_for(s, "part")
    assert st.code == "part" and st.title == "Партнёр"
    assert st.users == 3
    assert st.accepted == 2
    assert st.paying_users == 1
    assert st.stars == 199
    assert st.tribute_rub == 0
    assert st.generations_done == 1


async def test_stats_for_tribute_and_unresolved(session_factory):
    async with session_factory() as s:
        await referrals.create_code(s, "part", "Партнёр", None, 1)
        u = await repo.get_or_create_user(s, 1, "a")
        await referrals.attribute(s, u, "part")
        s.add(Payment(provider="tribute", external_id="t1", user_id=1, product="sub_month", amount=49900, currency="rub"))
        s.add(Payment(provider="tribute", external_id="t2", user_id=1, product="pack_50", amount=19900, currency=""))
        # заглушки неразобранных платежей в доход не идут
        s.add(Payment(provider="tribute", external_id="u9", user_id=1, product="?", amount=99900, currency="rub", status="unresolved"))
        s.add(Payment(provider="stars", external_id="u8", user_id=1, product="?", amount=500, currency="XTR", status="unresolved"))
        await s.commit()
    async with session_factory() as s:
        st = await referrals.stats_for(s, "part")
    assert st.tribute_rub == 698 and st.stars == 0 and st.paying_users == 1


async def test_stats_for_since_window(session_factory):
    async with session_factory() as s:
        await referrals.create_code(s, "part", "Партнёр", None, 1)
        old = await repo.get_or_create_user(s, 1, "a")
        await referrals.attribute(s, old, "part")
        old.rules_accepted_at = utcnow()
        old.ref_attributed_at = utcnow() - timedelta(days=30)
        fresh = await repo.get_or_create_user(s, 2, "b")
        await referrals.attribute(s, fresh, "part")
        p = Payment(provider="stars", external_id="c1", user_id=1, product="pack_50", amount=199, currency="XTR")
        p.created_at = utcnow() - timedelta(days=30)
        s.add(p)
        await s.commit()
    async with session_factory() as s:
        week = await referrals.stats_for(s, "part", utcnow() - timedelta(days=7))
        alltime = await referrals.stats_for(s, "part")
    assert (week.users, week.accepted, week.stars, week.paying_users) == (1, 0, 0, 0)
    assert (alltime.users, alltime.accepted, alltime.stars, alltime.paying_users) == (2, 1, 199, 1)


async def test_stats_all_covers_inactive_codes(session_factory):
    async with session_factory() as s:
        await _seed_three_users(s)
        await referrals.create_code(s, "sleepy", "Спящая", None, 1)
        await referrals.set_active(s, "sleepy", False)
        await s.commit()
    async with session_factory() as s:
        rows = await referrals.stats_all(s)
    assert [(r.code, r.users) for r in rows] == [("part", 3), ("sleepy", 0)]


class _AdminMessage:
    def __init__(self, admin_id=607396740):
        self.from_user = type("U", (), {"id": admin_id})()
        self.answers = []
        self.bot = _FakeBot()

    async def answer(self, text, **kw):
        self.answers.append(text)


class _FakeBot:
    async def me(self):
        return type("Me", (), {"username": "CucroBot"})()


async def test_admin_ref_commands(session_factory, monkeypatch):
    from bot import refs_view
    from bot.handlers.admin import refs as admin_refs

    monkeypatch.setattr(refs_view, "_cached_username", "CucroBot")

    async with session_factory() as s:
        msg = _AdminMessage()
        await admin_refs.cmd_ref_add(msg, CommandObject(args="Blog1 42 Блогер Вася"), s)
        await s.commit()
    assert msg.answers == [
        texts.ADM_REF_CREATED.format(title="Блогер Вася", link="https://t.me/CucroBot?start=ref_blog1")
    ]

    async with session_factory() as s:
        msg = _AdminMessage()
        await admin_refs.cmd_ref_add(msg, CommandObject(args="blog1 - Дубль"), s)
        assert msg.answers == [texts.ADM_REF_EXISTS]
        msg = _AdminMessage()
        await admin_refs.cmd_ref_add(msg, CommandObject(args="bad-code - Плохой"), s)
        assert msg.answers == [texts.ADM_REF_BAD_CODE]
        msg = _AdminMessage()
        await admin_refs.cmd_ref_add(msg, CommandObject(args="blog2 Вася Нет id"), s)
        assert msg.answers == [texts.ADM_USAGE_REF_ADD]
        msg = _AdminMessage()
        await admin_refs.cmd_ref_add(msg, CommandObject(args="blog2 42"), s)
        assert msg.answers == [texts.ADM_USAGE_REF_ADD]

    async with session_factory() as s:
        msg = _AdminMessage()
        await admin_refs.cmd_refs(msg, s)
    assert "https://t.me/CucroBot?start=ref_blog1" in msg.answers[0]
    assert "blog1 · Блогер Вася · 👥 0 (✅ 0) · 💳 0 · ⭐ 0 · ₽ 0 · 🖼 0" in msg.answers[0]
    assert texts.ADM_REF_OFF_MARK not in msg.answers[0]

    async with session_factory() as s:
        msg = _AdminMessage()
        await admin_refs.cmd_ref_off(msg, CommandObject(args="blog1"), s)
        await s.commit()
        assert msg.answers == [texts.ADM_REF_TOGGLED.format(code="blog1", state=texts.ADM_REF_STATE_OFF)]
    async with session_factory() as s:
        msg = _AdminMessage()
        await admin_refs.cmd_refs(msg, s)
        assert texts.ADM_REF_OFF_MARK + "blog1" in msg.answers[0]
        msg = _AdminMessage()
        await admin_refs.cmd_ref_on(msg, CommandObject(args="blog1"), s)
        await s.commit()
        assert msg.answers == [texts.ADM_REF_TOGGLED.format(code="blog1", state=texts.ADM_REF_STATE_ON)]
        msg = _AdminMessage()
        await admin_refs.cmd_ref_off(msg, CommandObject(args="nosuch"), s)
        assert msg.answers == [texts.ADM_REF_NOT_FOUND]
        msg = _AdminMessage()
        await admin_refs.cmd_ref_off(msg, CommandObject(args=""), s)
        assert msg.answers == [texts.ADM_USAGE_REF_TOGGLE]


async def test_refs_empty(session_factory, monkeypatch):
    from bot import refs_view
    from bot.handlers.admin import refs as admin_refs

    monkeypatch.setattr(refs_view, "_cached_username", "CucroBot")
    async with session_factory() as s:
        msg = _AdminMessage()
        await admin_refs.cmd_refs(msg, s)
        assert msg.answers == [texts.ADM_REFS_EMPTY]


async def test_partner_command(session_factory, monkeypatch):
    from bot import refs_view
    from bot.handlers.partner import cmd_partner

    monkeypatch.setattr(refs_view, "_cached_username", "CucroBot")

    async with session_factory() as s:
        msg = _AdminMessage(admin_id=99)
        await cmd_partner(msg, s)
        assert msg.answers == [texts.PARTNER_NONE]

    async with session_factory() as s:
        await _seed_three_users(s)  # код "part" принадлежит партнёру 99
        await s.commit()
    async with session_factory() as s:
        msg = _AdminMessage(admin_id=99)
        await cmd_partner(msg, s)
    text = msg.answers[0]
    assert "https://t.me/CucroBot?start=ref_part" in text
    assert "«Партнёр»" in text
    assert "Всего: 👥 3 (✅ 2) · 💳 1 · ⭐ 199 · ₽ 0 · 🖼 1" in text
    assert "7 дней: 👥 3 (✅ 2)" in text

    async with session_factory() as s:
        msg = _AdminMessage(admin_id=1234)
        await cmd_partner(msg, s)
        assert msg.answers == [texts.PARTNER_NONE]


async def test_bot_username_cached_once(monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", None)
    calls = []

    class Bot:
        async def me(self):
            calls.append(1)
            return type("Me", (), {"username": "CucroBot"})()

    assert await refs_view.bot_username(Bot()) == "CucroBot"
    assert await refs_view.bot_username(Bot()) == "CucroBot"
    assert len(calls) == 1
    monkeypatch.setattr(refs_view, "_cached_username", None)


async def _feed_start(monkeypatch, dispatcher, user_id: int, text: str) -> list[str]:
    from aiogram import Bot
    from aiogram.types import Chat, Message, MessageEntity, Update
    from aiogram.types import User as TgUser

    answers: list[str] = []

    async def fake_answer(self, text=None, **kwargs):
        answers.append(text)
        return None

    monkeypatch.setattr(Message, "answer", fake_answer)

    bot = Bot(token="42:TEST")
    update = Update(
        update_id=2,
        message=Message(
            message_id=1,
            date=datetime.now(),
            chat=Chat(id=user_id, type="private"),
            from_user=TgUser(id=user_id, is_bot=False, first_name="u"),
            text=text,
            entities=[MessageEntity(type="bot_command", offset=0, length=6)],
        ),
    )
    await dispatcher.feed_update(bot, update)
    await bot.session.close()
    return answers


async def test_start_with_ref_payload_attributes_and_shows_rules(
    dispatcher, dispatcher_session_factory, monkeypatch
):
    """Реальный Dispatcher: `/start ref_abc` от нового пользователя привязывает
    его к коду и всё равно показывает экран правил."""
    async with dispatcher_session_factory() as s:
        if await referrals.get_code(s, "abc") is None:
            await referrals.create_code(s, "abc", "Тест", None, 1)
        await s.commit()

    user_id = 770001
    answers = await _feed_start(monkeypatch, dispatcher, user_id, "/start ref_abc")

    assert texts.RULES in answers
    async with dispatcher_session_factory() as s:
        user = await repo.get_user(s, user_id)
    assert user is not None and user.ref_code == "abc" and user.ref_attributed_at is not None


async def test_plain_start_still_shows_rules(dispatcher, dispatcher_session_factory, monkeypatch):
    """Регрессия: `/start` без пейлоада работает как раньше."""
    user_id = 770002
    answers = await _feed_start(monkeypatch, dispatcher, user_id, "/start")
    assert texts.RULES in answers
    async with dispatcher_session_factory() as s:
        assert (await repo.get_user(s, user_id)).ref_code is None
