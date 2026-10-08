from datetime import timedelta
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import func, select

from bot import texts
from bot.channel_strikes import handle_downvote_threshold
from bot.channel_watch import GONE, scan_removed_posts
from bot.handlers.generate import gen_publish
from database.base import utcnow
from database.models import ChannelWarning, Generation, User
from database import repo
from services.channel_rank import published_count
from services.channel_strikes import (
    BAN_FOR,
    DOWNVOTES_TO_REMOVE,
    WARNING_WINDOW,
    WARNINGS_FOR_BAN,
    downvote_total,
    format_ban_until,
    record_strike,
)
from tests.test_channel import _Bot, _Cb, _ProbeBot, _State, _settings


def _vote(emoji, count):
    return SimpleNamespace(type=SimpleNamespace(emoji=emoji), total_count=count)


def _paid(count):
    return SimpleNamespace(type=SimpleNamespace(type="paid"), total_count=count)


def test_only_thumbs_down_count():
    reactions = [_vote("👍", 40), _vote("👎", 9), _vote("🔥", 3), _paid(2)]
    assert downvote_total(reactions) == 9
    assert downvote_total([_vote("👎", DOWNVOTES_TO_REMOVE)]) == 10


class _StrikeBot:
    def __init__(self, delete_error=None):
        self.deleted = []
        self.sent = []
        self.delete_error = delete_error

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))
        if self.delete_error:
            raise self.delete_error

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


async def _post(session, user_id, message_id):
    await repo.get_or_create_user(session, user_id, "u")
    gen = Generation(
        user_id=user_id, model_air="m", model_tier="base", actors=[], location="Офис",
        crystals_charged=1, status="done", result_file_id="photo",
        channel_message_id=message_id,
    )
    session.add(gen)
    await session.flush()
    return gen


async def test_nine_downvotes_leave_the_post(session_factory):
    async with session_factory() as s:
        await _post(s, 7, 55)
        await s.commit()
    bot = _StrikeBot()
    await handle_downvote_threshold(bot, session_factory, -100777, 55, 9)
    assert bot.deleted == []
    assert bot.sent == []
    async with session_factory() as s:
        assert await s.scalar(select(func.count()).select_from(ChannelWarning)) == 0


async def test_tenth_downvote_removes_the_post_and_warns_once(session_factory):
    async with session_factory() as s:
        await _post(s, 7, 55)
        await s.commit()
    bot = _StrikeBot()
    await handle_downvote_threshold(bot, session_factory, -100777, 55, 10)
    assert bot.deleted == [(-100777, 55)]
    assert bot.sent == [(7, texts.CHANNEL_STRIKE.format(n=1))]
    async with session_factory() as s:
        gen = (await s.execute(select(Generation).where(Generation.channel_message_id == 55))).scalar_one()
        assert gen.channel_removed_at is not None
        assert await published_count(s, 7) == 1
        user = await s.get(User, 7)
        assert user.channel_ban_until is None
    again = _StrikeBot(delete_error=TelegramBadRequest(None, "Bad Request: message to delete not found"))
    await handle_downvote_threshold(again, session_factory, -100777, 55, 12)
    assert again.deleted == [(-100777, 55)]
    assert again.sent == []


async def test_third_warning_in_a_week_bans_posting_for_a_month(session_factory):
    now = utcnow()
    async with session_factory() as s:
        gens = [await _post(s, 7, 100 + i) for i in range(3)]
        await s.commit()
        ids = [g.id for g in gens]
    async with session_factory() as s:
        for i, gen_id in enumerate(ids, start=1):
            gen = await s.get(Generation, gen_id)
            strike = await record_strike(s, gen, now)
            await s.commit()
        user = await s.get(User, 7)
        assert strike is not None
        assert strike.warnings == WARNINGS_FOR_BAN
        assert user.channel_ban_until is not None
        assert user.channel_ban_until - now == BAN_FOR
    bot = _StrikeBot()
    await handle_downvote_threshold(bot, session_factory, -100777, 102, 10)
    assert bot.sent == []


async def test_warning_older_than_a_week_does_not_count(session_factory):
    now = utcnow()
    async with session_factory() as s:
        old = await _post(s, 7, 1)
        fresh = [await _post(s, 7, 2), await _post(s, 7, 3)]
        await s.commit()
        old_id, fresh_ids = old.id, [g.id for g in fresh]
    async with session_factory() as s:
        await record_strike(s, await s.get(Generation, old_id), now - WARNING_WINDOW - timedelta(seconds=1))
        await s.commit()
        for gen_id in fresh_ids:
            strike = await record_strike(s, await s.get(Generation, gen_id), now)
            await s.commit()
        user = await s.get(User, 7)
    assert strike.warnings == 2
    assert strike.ban_until is None
    assert user.channel_ban_until is None


async def test_a_new_ban_does_not_shorten_a_longer_one(session_factory):
    now = utcnow()
    longer = now + timedelta(days=60)
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 7, "u")
        user.channel_ban_until = longer
        gens = [await _post(s, 7, 10 + i) for i in range(3)]
        await s.commit()
        ids = [g.id for g in gens]
    async with session_factory() as s:
        for gen_id in ids:
            await record_strike(s, await s.get(Generation, gen_id), now)
            await s.commit()
        user = await s.get(User, 7)
    assert user.channel_ban_until == longer


async def test_banned_user_cannot_publish_until_the_date(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", "Cucrobot")
    until = utcnow() + timedelta(days=12)
    async with session_factory() as s:
        user = await repo.get_or_create_user(s, 1, "u")
        user.channel_ban_until = until
        gen = Generation(
            user_id=1, model_air="m", model_tier="base", actors=[], location="Офис",
            crystals_charged=1, status="done", result_file_id="photo-1",
        )
        s.add(gen)
        await s.commit()
        gen_id = gen.id

    bot = _Bot()
    cb = _Cb(bot)
    state = _State({"people": ["a"], "actors": [1], "scene_id": 3, "last_generation_id": gen_id})
    async with session_factory() as s:
        user = await repo.get_user(s, 1)
        await gen_publish(cb, state, s, user, _settings(channel_id="-100777"))
    assert bot.photos == []
    assert cb.alerts[-1] == (texts.CHANNEL_POST_BANNED.format(until=format_ban_until(until)), True)

    async with session_factory() as s:
        user = await repo.get_user(s, 1)
        user.channel_ban_until = utcnow() - timedelta(minutes=1)
        await s.commit()
    async with session_factory() as s:
        user = await repo.get_user(s, 1)
        await gen_publish(cb, state, s, user, _settings(channel_id="-100777"))
        await s.commit()
    assert len(bot.photos) == 1


async def test_third_live_strike_tells_the_ban_date(session_factory):
    async with session_factory() as s:
        for i in range(3):
            await _post(s, 7, 30 + i)
        await s.commit()
    bot = _StrikeBot()
    for message_id in (30, 31, 32):
        await handle_downvote_threshold(bot, session_factory, -100777, message_id, 10)
    assert len(bot.deleted) == 3
    assert bot.sent[0] == (7, texts.CHANNEL_STRIKE.format(n=1))
    assert bot.sent[1] == (7, texts.CHANNEL_STRIKE.format(n=2))
    assert "В канал нельзя постить до " in bot.sent[2][1]
    async with session_factory() as s:
        user = await s.get(User, 7)
        assert format_ban_until(user.channel_ban_until) in bot.sent[2][1]


async def test_watch_does_not_repeat_a_strike_notice(session_factory, monkeypatch):
    from bot import refs_view

    monkeypatch.setattr(refs_view, "_cached_username", "Cucrobot")

    async def gone_after_strike(bot, chat_id, message_id, reply_markup):
        async with session_factory() as s:
            gen = (await s.execute(select(Generation).where(Generation.channel_message_id == message_id))).scalar_one()
            gen.channel_removed_at = utcnow()
            await s.commit()
        return GONE

    monkeypatch.setattr("bot.channel_watch.probe_post", gone_after_strike)
    async with session_factory() as s:
        await _post(s, 7, 55)
        await s.commit()
    bot = _ProbeBot()
    await scan_removed_posts(bot, session_factory, -100777, pause=0)
    assert bot.sent == []


def test_polling_listens_for_reaction_counts(dispatcher):
    assert "message_reaction_count" in dispatcher.resolve_used_update_types()


@pytest.mark.parametrize("text", [texts.CHANNEL_STRIKE.format(n=1), texts.CHANNEL_STRIKE_BAN.format(until="01.01.2027 12:00"), texts.CHANNEL_POST_BANNED.format(until="01.01.2027 12:00")])
def test_strike_texts_fit_a_telegram_alert(text):
    assert len(text) <= 200
