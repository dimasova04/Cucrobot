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
    add_refs = State()


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
        try:
            await catalog.set_actor_active(session, aid, not actor.is_active)
        except ValueError:
            await cb.answer(texts.ADM_ACTOR_NEEDS_PHOTOS.format(n=catalog.MIN_REFS - len(actor.refs)), show_alert=True)
            return
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


async def _refs_done(target: Message, state: FSMContext, session, actor_id: int):
    actor = await catalog.get_actor(session, actor_id)
    await state.clear()
    if actor:
        state_word = texts.ADM_ON if actor.is_active else texts.ADM_OFF
        await target.answer(texts.ADM_ACTOR_REFS_SAVED.format(n=len(actor.refs), state=state_word))
    await _list(target, session)


@actors_router.callback_query(F.data.startswith("adm:actor:addrefs:"))
async def cb_addrefs(cb: CallbackQuery, state: FSMContext):
    aid = int(cb.data.rsplit(":", 1)[1])
    await cb.answer()
    await state.set_state(AdminActorStates.add_refs)
    await state.set_data({"actor_id": aid})
    await cb.message.answer(texts.ADM_ACTOR_MORE_PHOTOS, reply_markup=keyboards.grid([(texts.ADM_DONE, "adm:actor:refsdone")], 1))


@actors_router.message(AdminActorStates.add_refs, F.photo | F.document)
async def st_add_refs_photo(message: Message, state: FSMContext, session):
    fid = _photo_file_id(message)
    if not fid:
        await message.answer(texts.NOT_A_PHOTO)
        return
    d = await state.get_data()
    aid = d["actor_id"]
    actor = await catalog.add_actor_refs(session, aid, [fid])
    if len(actor.refs) >= catalog.MAX_REFS:
        await _refs_done(message, state, session, aid)
        return
    await message.answer(
        texts.ADM_ACTOR_PHOTO_OK.format(n=len(actor.refs)),
        reply_markup=keyboards.grid([(texts.ADM_DONE, "adm:actor:refsdone")], 1),
    )


@actors_router.callback_query(AdminActorStates.add_refs, F.data == "adm:actor:refsdone")
async def cb_refs_done(cb: CallbackQuery, state: FSMContext, session):
    await cb.answer()
    d = await state.get_data()
    await _refs_done(cb.message, state, session, d["actor_id"])


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
    if len(actor.refs) < catalog.MIN_REFS:
        text += "\n" + texts.ADM_ACTOR_NEEDS_PHOTOS.format(n=catalog.MIN_REFS - len(actor.refs))
    kb = keyboards.grid(
        [
            (texts.ADM_TOGGLE, f"adm:actor:toggle:{aid}"),
            (texts.ADM_SHOW_REFS, f"adm:actor:refs:{aid}"),
            (texts.ADM_ADD_PHOTOS, f"adm:actor:addrefs:{aid}"),
            (texts.ADM_DELETE, f"adm:actor:del:{aid}"),
        ],
        2, [[(texts.ADM_BACK, "adm:actor:list")]],
    )
    await cb.message.answer(text, reply_markup=kb)
