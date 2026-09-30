from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from loguru import logger

from bot import texts
from bot.refs_view import bot_username, stats_line
from services import referrals

refs_router = Router(name="admin_refs")


@refs_router.message(Command("ref_add"))
async def cmd_ref_add(message: Message, command: CommandObject, session):
    parts = (command.args or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(texts.ADM_USAGE_REF_ADD)
        return
    raw_code, raw_partner, title = parts
    code = referrals.normalize_code(raw_code)
    if code is None:
        await message.answer(texts.ADM_REF_BAD_CODE)
        return
    if raw_partner == "-":
        partner_id = None
    elif raw_partner.isdigit():
        partner_id = int(raw_partner)
    else:
        await message.answer(texts.ADM_USAGE_REF_ADD)
        return
    try:
        rc = await referrals.create_code(session, code, title, partner_id, message.from_user.id)
    except ValueError:
        await message.answer(texts.ADM_REF_EXISTS)
        return
    logger.info("admin {} created ref code {} for partner {}", message.from_user.id, rc.code, partner_id)
    link = referrals.link_for(await bot_username(message.bot), rc.code)
    await message.answer(texts.ADM_REF_CREATED.format(title=rc.title, link=link))


@refs_router.message(Command("refs"))
async def cmd_refs(message: Message, session):
    rows = await referrals.stats_all(session)
    if not rows:
        await message.answer(texts.ADM_REFS_EMPTY)
        return
    username = await bot_username(message.bot)
    active = {rc.code: rc.is_active for rc in await referrals.list_codes(session)}
    blocks = [texts.ADM_REFS_HEADER]
    for st in rows:
        mark = "" if active.get(st.code, True) else texts.ADM_REF_OFF_MARK
        blocks.append(stats_line(st, texts.REF_LINE, mark) + "\n" + referrals.link_for(username, st.code))
    await message.answer("\n\n".join(blocks), disable_web_page_preview=True)


async def _toggle(message: Message, command: CommandObject, session, active: bool):
    code = referrals.normalize_code((command.args or "").strip())
    if code is None:
        await message.answer(texts.ADM_USAGE_REF_TOGGLE)
        return
    rc = await referrals.set_active(session, code, active)
    if rc is None:
        await message.answer(texts.ADM_REF_NOT_FOUND)
        return
    state = texts.ADM_REF_STATE_ON if active else texts.ADM_REF_STATE_OFF
    await message.answer(texts.ADM_REF_TOGGLED.format(code=rc.code, state=state))


@refs_router.message(Command("ref_off"))
async def cmd_ref_off(message: Message, command: CommandObject, session):
    await _toggle(message, command, session, False)


@refs_router.message(Command("ref_on"))
async def cmd_ref_on(message: Message, command: CommandObject, session):
    await _toggle(message, command, session, True)
