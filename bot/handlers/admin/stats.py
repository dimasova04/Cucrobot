from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from loguru import logger
from sqlalchemy import func, select

from bot import texts
from database import repo
from database.models import Generation
from services import stats
from services.billing import subscriptions, wallet
from services.billing.products import SUBS

stats_router = Router(name="admin_stats")


@stats_router.message(Command("admin"))
async def cmd_admin_help(message: Message):
    await message.answer(texts.ADM_HELP)


@stats_router.message(Command("stats"))
async def cmd_stats(message: Message, session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    month_from, month_title = stats.month_start(now)
    today = stats.day_start(now)
    sm = await stats.collect(session, month_from)
    s1 = await stats.collect(session, today)
    t = await stats.totals(session, now)
    await message.answer(texts.ADM_STATS.format(
        month=month_title,
        mu=sm.new_users, ma=sm.accepted, mpayers=sm.payers, mp=sm.payments,
        ms=sm.stars, mt=sm.tribute_rub,
        mgb=sm.generations.get("base", 0), mgp=sm.generations.get("premium", 0),
        mc=sm.cost_usd,
        u1=s1.new_users,
        g1b=s1.generations.get("base", 0), g1p=s1.generations.get("premium", 0),
        s1=s1.stars, t1=s1.tribute_rub,
        users=t.users, accepted=t.accepted, subs=t.active_subs, gens=t.generations_done, crystals=t.crystals_in_wallets,
        ref_users=t.ref_users,
    ), parse_mode="HTML")


@stats_router.message(Command("give"))
async def cmd_give(message: Message, command: CommandObject, session):
    parts = (command.args or "").split()
    if len(parts) != 2 or not all(p.lstrip("-").isdigit() for p in parts):
        await message.answer(texts.ADM_USAGE_GIVE)
        return
    uid, n = int(parts[0]), int(parts[1])
    if await repo.get_user(session, uid) is None:
        await message.answer(texts.ADM_USER_NOT_FOUND)
        return
    try:
        balance = await wallet.apply(session, uid, n, "admin", "admin", str(message.from_user.id))
    except wallet.InsufficientCrystals as e:
        await message.answer(texts.ADM_GIVE_INSUFFICIENT.format(balance=e.balance))
        return
    await message.answer(texts.ADM_GIVE_OK.format(n=n, uid=uid, balance=balance))


@stats_router.message(Command("sub"))
async def cmd_sub(message: Message, command: CommandObject, session):
    parts = (command.args or "").split()
    plans = {p.code: p for p in SUBS}
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in plans:
        await message.answer(texts.ADM_USAGE_SUB)
        return
    user = await repo.get_user_for_update(session, int(parts[0]))
    if user is None:
        await message.answer(texts.ADM_USER_NOT_FOUND)
        return
    until = subscriptions.extend(user, parts[1], plans[parts[1]].days)
    await message.answer(texts.ADM_SUB_OK.format(plan=texts.PLAN_NAMES[parts[1]], uid=user.id, until=until.strftime("%d.%m.%Y")))


async def _set_blocked(message: Message, command: CommandObject, session, blocked: bool, ok_text: str):
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer(texts.ADM_USAGE_BLOCK)
        return
    user = await repo.get_user_for_update(session, int(arg))
    if user is None:
        await message.answer(texts.ADM_USER_NOT_FOUND)
        return
    user.is_blocked = blocked
    await session.flush()
    logger.info("admin {} set is_blocked={} for {}", message.from_user.id, blocked, user.id)
    await message.answer(ok_text.format(uid=user.id))


@stats_router.message(Command("block"))
async def cmd_block(message: Message, command: CommandObject, session):
    await _set_blocked(message, command, session, True, texts.ADM_BLOCK_OK)


@stats_router.message(Command("unblock"))
async def cmd_unblock(message: Message, command: CommandObject, session):
    await _set_blocked(message, command, session, False, texts.ADM_UNBLOCK_OK)


@stats_router.message(Command("user"))
async def cmd_user(message: Message, command: CommandObject, session):
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer(texts.ADM_USAGE_USER)
        return
    user = await repo.get_user(session, int(arg))
    if user is None:
        await message.answer(texts.ADM_USER_NOT_FOUND)
        return
    gens = (await session.execute(select(func.count()).select_from(Generation).where(Generation.user_id == user.id))).scalar_one()
    sub = texts.SUB_ACTIVE.format(plan=texts.PLAN_NAMES.get(user.sub_plan, user.sub_plan), until=user.sub_until.strftime("%d.%m.%Y")) if subscriptions.is_active(user) else texts.SUB_NONE
    await message.answer(texts.ADM_USER_CARD.format(uid=user.id, username=user.username or "-", crystals=user.crystals, sub=sub, gens=gens, created=user.created_at.strftime("%d.%m.%Y")))
