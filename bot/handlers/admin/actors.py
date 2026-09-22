from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from bot import keyboards, texts
from services import catalog
from services.generation.content_filter import is_allowed

actors_router = Router(name="admin_actors")


class AdminActorStates(StatesGroup):
    name = State()
    description = State()
    photos = State()


# Зарегистрирован первым: иначе /cancel внутри диалога съели бы текстовые шаги.
# Ограничен состояниями этого диалога: иначе не-админы, для которых фильтр
# Command всё равно матчится раньше AdminOnlyMiddleware, никогда не доходили
# бы до menu_router.cmd_cancel.
@actors_router.message(Command("cancel"), StateFilter(AdminActorStates))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(texts.CANCELLED, reply_markup=keyboards.main_menu())


def _photo_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document.file_id
    return None


async def _list(target: Message, session):
    actors = await catalog.list_actors(session, active_only=False)
    items = [(f"{'✅' if a.is_active else '⛔'} {a.name} ({len(a.refs)})", f"adm:actor:{a.id}") for a in actors]
    await target.answer(texts.ADM_ACTORS, reply_markup=keyboards.grid(items, 2, [[(texts.ADM_ADD, "adm:actor:add")]]))


@actors_router.message(Command("actors"))
async def cmd_actors(message: Message, session, state: FSMContext):
    await state.clear()
    await _list(message, session)


@actors_router.callback_query(F.data == "adm:actor:list")
async def cb_list(cb: CallbackQuery, session):
    await cb.answer()
    await _list(cb.message, session)


@actors_router.callback_query(F.data == "adm:actor:add")
async def cb_add(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminActorStates.name)
    await state.set_data({"files": []})
    await cb.message.answer(texts.ADM_ACTOR_NAME)


@actors_router.message(AdminActorStates.name, F.text)
async def st_name(message: Message, state: FSMContext):
    if len(message.text) > 64:
        await message.answer(texts.ADM_TOO_LONG)
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminActorStates.description)
    await message.answer(texts.ADM_ACTOR_DESC)


@actors_router.message(AdminActorStates.description, F.text)
async def st_desc(message: Message, state: FSMContext):
    if len(message.text) > 200:
        await message.answer(texts.ADM_TOO_LONG)
        return
    if not is_allowed(message.text):
        await message.answer(texts.ADM_TEXT_REJECTED)
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(AdminActorStates.photos)
    await message.answer(texts.ADM_ACTOR_PHOTOS, reply_markup=keyboards.grid([(texts.ADM_DONE, "adm:actor:done")], 1))


async def _create(target: Message, state: FSMContext, session, admin_id: int):
    d = await state.get_data()
    actor = await catalog.create_actor(session, d["name"], d["description"], d["files"], admin_id)
    await state.clear()
    await target.answer(texts.ADM_ACTOR_CREATED.format(name=actor.name))
    await _list(target, session)


@actors_router.message(AdminActorStates.photos, F.photo | F.document)
async def st_photo(message: Message, state: FSMContext, session):
    fid = _photo_file_id(message)
    if not fid:
        await message.answer(texts.NOT_A_PHOTO)
        return
    d = await state.get_data()
    d["files"].append(fid)
    await state.set_data(d)
    if len(d["files"]) >= catalog.MAX_REFS:
        await _create(message, state, session, message.from_user.id)
        return
    await message.answer(texts.ADM_ACTOR_PHOTO_OK.format(n=len(d["files"])), reply_markup=keyboards.grid([(texts.ADM_DONE, "adm:actor:done")], 1))


@actors_router.callback_query(AdminActorStates.photos, F.data == "adm:actor:done")
async def st_done(cb: CallbackQuery, state: FSMContext, session):
    await cb.answer()
    d = await state.get_data()
    if len(d["files"]) < catalog.MIN_REFS:
        await cb.message.answer(texts.ADM_ACTOR_NEED_MORE)
        return
    await _create(cb.message, state, session, cb.from_user.id)


@actors_router.callback_query(F.data.startswith("adm:actor:toggle:"))
async def cb_toggle(cb: CallbackQuery, session):
    aid = int(cb.data.rsplit(":", 1)[1])
    actor = await catalog.get_actor(session, aid)
    if actor:
        await catalog.set_actor_active(session, aid, not actor.is_active)
    await cb.answer()
    await _list(cb.message, session)


@actors_router.callback_query(F.data.startswith("adm:actor:del:"))
async def cb_delete(cb: CallbackQuery, session):
    await catalog.delete_actor(session, int(cb.data.rsplit(":", 1)[1]))
    await cb.answer(texts.ADM_DELETED)
    await _list(cb.message, session)


@actors_router.callback_query(F.data.startswith("adm:actor:refs:"))
async def cb_refs(cb: CallbackQuery, session):
    actor = await catalog.get_actor(session, int(cb.data.rsplit(":", 1)[1]))
    await cb.answer()
    if actor and actor.refs:
        await cb.message.answer_media_group([InputMediaPhoto(media=r.file_id) for r in actor.refs])


@actors_router.callback_query(F.data.regexp(r"^adm:actor:\d+$"))
async def cb_card(cb: CallbackQuery, session):
    aid = int(cb.data.rsplit(":", 1)[1])
    actor = await catalog.get_actor(session, aid)
    await cb.answer()
    if not actor:
        return
    text = texts.ADM_ACTOR_CARD.format(
        name=actor.name, description=actor.description, refs=len(actor.refs),
        active=texts.ADM_YES if actor.is_active else texts.ADM_NO,
    )
    kb = keyboards.grid(
        [(texts.ADM_TOGGLE, f"adm:actor:toggle:{aid}"), (texts.ADM_SHOW_REFS, f"adm:actor:refs:{aid}"), (texts.ADM_DELETE, f"adm:actor:del:{aid}")],
        2, [[(texts.ADM_BACK, "adm:actor:list")]],
    )
    await cb.message.answer(text, reply_markup=kb)
