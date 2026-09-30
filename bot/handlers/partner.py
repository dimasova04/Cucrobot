from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot import texts
from bot.refs_view import bot_username, short_line
from database.base import utcnow
from services import referrals

partner_router = Router(name="partner")


@partner_router.message(Command("partner"))
async def cmd_partner(message: Message, session):
    """Статистика партнёра по его собственным реф-ссылкам. Не админская команда."""
    codes = await referrals.codes_for_partner(session, message.from_user.id)
    if not codes:
        await message.answer(texts.PARTNER_NONE)
        return
    week_ago = utcnow() - timedelta(days=7)
    username = await bot_username(message.bot)
    blocks = [texts.PARTNER_HEADER]
    for rc in codes:
        all_time = await referrals.stats_for(session, rc.code)
        week = await referrals.stats_for(session, rc.code, week_ago)
        blocks.append(texts.PARTNER_BLOCK.format(
            title=rc.title,
            link=referrals.link_for(username, rc.code),
            all_line=short_line(all_time),
            week_line=short_line(week),
        ))
    await message.answer("\n\n".join(blocks), disable_web_page_preview=True)
