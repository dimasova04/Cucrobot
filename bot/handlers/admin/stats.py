from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select

from bot import texts
from database import repo
from database.models import Generation
from services import stats
from services.billing import subscriptions, wallet
from services.billing.products import SUBS

stats_router = Router(name="admin_stats")


@stats_router.message(Command("stats"))
async def cmd_stats(message: Message, session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    s1 = await stats.collect(session, today)
    s7 = await stats.collect(session, now - timedelta(days=7))
    await message.answer(texts.ADM_STATS.format(
        u1=s1.new_users, u7=s7.new_users,
        g1b=s1.generations.get("base", 0), g1p=s1.generations.get("premium", 0),
        g7b=s7.generations.get("base", 0), g7p=s7.generations.get("premium", 0),
        c1=s1.cost_usd, c7=s7.cost_usd, s1=s1.stars, s7=s7.stars, t1=s1.tribute_rub, t7=s7.tribute_rub,
    ))


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
    balance = await wallet.apply(session, uid, n, "admin", "admin", str(message.from_user.id))
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
