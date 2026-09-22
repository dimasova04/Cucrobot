from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import keyboards, texts
from services import catalog
from services.generation.content_filter import is_allowed

scenes_router = Router(name="admin_scenes")


class AdminSceneStates(StatesGroup):
    name = State()
    prompt = State()
    orientation = State()
    photo = State()


def _photo_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document.file_id
    return None


async def _list(target: Message, session):
    scenes = await catalog.list_scenes(session, active_only=False)
    items = [(f"{'✅' if s.is_active else '⛔'} {s.name}", f"adm:scene:{s.id}") for s in scenes]
    await target.answer(texts.ADM_SCENES, reply_markup=keyboards.grid(items, 2, [[(texts.ADM_ADD, "adm:scene:add")]]))


@scenes_router.message(Command("scenes"))
async def cmd_scenes(message: Message, session, state: FSMContext):
    await state.clear()
    await _list(message, session)


@scenes_router.callback_query(F.data == "adm:scene:list")
async def cb_list(cb: CallbackQuery, session):
    await cb.answer()
    await _list(cb.message, session)


@scenes_router.callback_query(F.data == "adm:scene:add")
async def cb_add(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminSceneStates.name)
    await state.set_data({})
    await cb.message.answer(texts.ADM_SCENE_NAME)


@scenes_router.message(AdminSceneStates.name, F.text)
async def st_name(message: Message, state: FSMContext):
    if len(message.text) > 64:
        await message.answer(texts.ADM_TOO_LONG)
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminSceneStates.prompt)
    await message.answer(texts.ADM_SCENE_PROMPT)


@scenes_router.message(AdminSceneStates.prompt, F.text)
async def st_prompt(message: Message, state: FSMContext):
    if len(message.text) > 300:
        await message.answer(texts.ADM_TOO_LONG)
        return
    if not is_allowed(message.text):
        await message.answer(texts.ADM_TEXT_REJECTED)
        return
    await state.update_data(prompt=message.text.strip())
    await state.set_state(AdminSceneStates.orientation)
    await message.answer(texts.ADM_SCENE_ORIENT, reply_markup=keyboards.grid([(texts.ADM_PORTRAIT, "adm:scene:or:portrait"), (texts.ADM_LANDSCAPE, "adm:scene:or:landscape")], 2))


@scenes_router.callback_query(AdminSceneStates.orientation, F.data.startswith("adm:scene:or:"))
async def st_orientation(cb: CallbackQuery, state: FSMContext):
    await state.update_data(orientation=cb.data.rsplit(":", 1)[1])
    await state.set_state(AdminSceneStates.photo)
    await cb.answer()
    await cb.message.answer(texts.ADM_SCENE_PHOTO, reply_markup=keyboards.grid([(texts.ADM_NO_PHOTO, "adm:scene:nophoto")], 1))


async def _create(target: Message, state: FSMContext, session, admin_id: int, file_id: str | None):
    d = await state.get_data()
    scene = await catalog.create_scene(session, d["name"], d["prompt"], d["orientation"], file_id, admin_id)
    await state.clear()
    await target.answer(texts.ADM_SCENE_CREATED.format(name=scene.name))
    await _list(target, session)


@scenes_router.message(AdminSceneStates.photo, F.photo | F.document)
async def st_photo(message: Message, state: FSMContext, session):
    fid = _photo_file_id(message)
    if not fid:
        await message.answer(texts.NOT_A_PHOTO)
        return
    await _create(message, state, session, message.from_user.id, fid)


@scenes_router.callback_query(AdminSceneStates.photo, F.data == "adm:scene:nophoto")
async def st_nophoto(cb: CallbackQuery, state: FSMContext, session):
    await cb.answer()
    await _create(cb.message, state, session, cb.from_user.id, None)


@scenes_router.callback_query(F.data.startswith("adm:scene:toggle:"))
async def cb_toggle(cb: CallbackQuery, session):
    sid = int(cb.data.rsplit(":", 1)[1])
    scene = await catalog.get_scene(session, sid)
    if scene:
        await catalog.set_scene_active(session, sid, not scene.is_active)
    await cb.answer()
    await _list(cb.message, session)


@scenes_router.callback_query(F.data.startswith("adm:scene:del:"))
async def cb_delete(cb: CallbackQuery, session):
    await catalog.delete_scene(session, int(cb.data.rsplit(":", 1)[1]))
    await cb.answer(texts.ADM_DELETED)
    await _list(cb.message, session)


@scenes_router.callback_query(F.data.regexp(r"^adm:scene:\d+$"))
async def cb_card(cb: CallbackQuery, session):
    sid = int(cb.data.rsplit(":", 1)[1])
    scene = await catalog.get_scene(session, sid)
    await cb.answer()
    if not scene:
        return
    text = f"{scene.name}\n{scene.prompt}\nОриентация: {scene.orientation}\nФото: {'есть' if scene.ref_file_id else 'нет'}\nАктивна: {'да' if scene.is_active else 'нет'}"
    kb = keyboards.grid([(texts.ADM_TOGGLE, f"adm:scene:toggle:{sid}"), (texts.ADM_DELETE, f"adm:scene:del:{sid}")], 2, [[(texts.ADM_BACK, "adm:scene:list")]])
    if scene.ref_file_id:
        await cb.message.answer_photo(scene.ref_file_id, caption=text, reply_markup=kb)
    else:
        await cb.message.answer(text, reply_markup=kb)
