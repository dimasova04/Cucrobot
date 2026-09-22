from datetime import timedelta

from aiogram import F, Router
from aiogram.types import Message

from bot import keyboards, texts
from services.billing import bonus, subscriptions

balance_router = Router(name="balance")


def _fmt_wait(wait: timedelta) -> str:
    total = int(wait.total_seconds())
    return texts.BONUS_WAIT.format(hours=total // 3600, minutes=(total % 3600) // 60)


def _sub_text(user) -> str:
    if subscriptions.is_active(user):
        return texts.SUB_ACTIVE.format(plan=texts.PLAN_NAMES.get(user.sub_plan, user.sub_plan), until=user.sub_until.strftime("%d.%m.%Y"))
    return texts.SUB_NONE


@balance_router.message(F.text == texts.BTN_BALANCE)
async def show_balance(message: Message, user, settings):
    st = bonus.bonus_status(user, settings)
    bonus_txt = texts.BONUS_READY if st.ready else _fmt_wait(st.wait)
    await message.answer(texts.BALANCE.format(crystals=user.crystals, sub=_sub_text(user), bonus=bonus_txt), reply_markup=keyboards.main_menu())


@balance_router.message(F.text == texts.BTN_BONUS)
async def claim(message: Message, session, user, settings):
    res = await bonus.claim_bonus(session, user.id, settings)
    if isinstance(res, bonus.BonusStatus):
        await message.answer(texts.BONUS_NOT_READY.format(when=_fmt_wait(res.wait)))
        return
    amount, balance = res
    await message.answer(texts.BONUS_CLAIMED.format(n=amount, balance=balance))
