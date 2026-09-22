import asyncio

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from loguru import logger

from bot import keyboards, texts
from bot.bonus_card import send_bonus_card
from bot.flow import (
    ACTORS_PER_PAGE,
    SCENES_PER_PAGE,
    GenStates,
    empty_data,
    is_complete,
    paginate,
    request_from_state,
    scene_label,
    summary,
    validate_custom_scene,
    validate_detail,
)
from database.models import Generation
from services import catalog
from services.billing import subscriptions, wallet
from services.generation import faces
from services.generation.generator import AlreadyRunning

generate_router = Router(name="generate")


def _photo_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document.file_id
    return None


async def _start_flow(message: Message, state: FSMContext):
    await state.clear()
    await state.set_data(empty_data())
    await state.set_state(GenStates.person1)
    await message.answer(texts.SEND_PERSON_1, reply_markup=keyboards.grid([], extra_rows=[keyboards.cancel_row()]))


@generate_router.message(F.text == texts.BTN_CREATE)
async def btn_create(message: Message, state: FSMContext):
    await _start_flow(message, state)


def _nav_row(prefix: str, page: int, has_prev: bool, has_next: bool) -> list[list[tuple[str, str]]]:
    row = []
    if has_prev:
        row.append((texts.BTN_PREV, f"{prefix}:page:{page - 1}"))
    if has_next:
        row.append((texts.BTN_NEXT, f"{prefix}:page:{page + 1}"))
    return [row] if row else []


async def _show_actors(
    target: Message, state: FSMContext, session,
    exclude: list[int] | None = None, second: bool = False, page: int = 0,
):
    all_actors = await catalog.list_actors(session)
    if not all_actors:
        await state.clear()
        await target.answer(texts.CATALOG_EMPTY, reply_markup=keyboards.main_menu())
        return
    actors = [a for a in all_actors if a.id not in (exclude or [])]
    chunk, has_prev, has_next = paginate(actors, page, ACTORS_PER_PAGE)
    items = [(a.name, f"act:{a.id}") for a in chunk]
    extra = _nav_row("act", page, has_prev, has_next)
    if second:
        extra.append([(texts.BTN_NO, "a2:no")])
    elif len((await state.get_data()).get("people", [])) < 2:
        extra.append([(texts.BTN_ADD_PERSON, "act:addperson")])
    extra.append(keyboards.cancel_row())
    await state.set_state(GenStates.actor2 if second else GenStates.actor1)
    await target.answer(texts.CHOOSE_ACTOR_2 if second else texts.CHOOSE_ACTOR, reply_markup=keyboards.grid(items, 2, extra))


async def _show_scenes(target: Message, state: FSMContext, session, page: int = 0):
    scenes = await catalog.list_scenes(session)
    chunk, has_prev, has_next = paginate(scenes, page, SCENES_PER_PAGE)
    items = [(s.name, f"scene:{s.id}") for s in chunk]
    extra = _nav_row("scene", page, has_prev, has_next)
    extra.append([(texts.BTN_CUSTOM_SCENE, "scene:custom")])
    extra.append(keyboards.cancel_row())
    await state.set_state(GenStates.scene)
    await target.answer(texts.CHOOSE_SCENE, reply_markup=keyboards.grid(items, 2, extra))


@generate_router.message(GenStates.person1, F.photo | F.document)
@generate_router.message(GenStates.person2, F.photo | F.document)
async def got_person_photo(message: Message, state: FSMContext, session, bot: Bot):
    file_id = _photo_file_id(message)
    if not file_id:
        await message.answer(texts.NOT_A_PHOTO)
        return
    data = (await bot.download(file_id)).read()
    # OpenCV блокирует поток: держим event loop свободным, пока идёт детекция.
    if not await asyncio.to_thread(faces.has_face, data):
        await message.answer(texts.NO_FACE)
        return
    st = await state.get_data()
    st["people"].append(file_id)
    await state.set_data(st)
    await _show_actors(message, state, session)


@generate_router.message(GenStates.person1)
@generate_router.message(GenStates.person2)
async def not_a_photo(message: Message):
    await message.answer(texts.NOT_A_PHOTO)


# Зарегистрирован раньше act:<id>: кнопка «добавить человека» в списке актёров.
@generate_router.callback_query(GenStates.actor1, F.data == "act:addperson")
async def add_person(cb: CallbackQuery, state: FSMContext):
    st = await state.get_data()
    await cb.answer()
    if len(st.get("people", [])) >= 2:
        return
    await state.set_state(GenStates.person2)
    await cb.message.answer(texts.SEND_PERSON_2)


# Зарегистрирован раньше act:<id>, иначе "act:page:2" попал бы в выбор актёра.
@generate_router.callback_query(GenStates.actor1, F.data.startswith("act:page:"))
@generate_router.callback_query(GenStates.actor2, F.data.startswith("act:page:"))
async def actors_page(cb: CallbackQuery, state: FSMContext, session):
    page = int(cb.data.rsplit(":", 1)[1])
    st = await state.get_data()
    second = await state.get_state() == GenStates.actor2.state
    await cb.answer()
    await _show_actors(cb.message, state, session, exclude=st.get("actors") if second else None, second=second, page=page)


@generate_router.callback_query(GenStates.actor1, F.data.startswith("act:"))
async def actor1_chosen(cb: CallbackQuery, state: FSMContext, session):
    actor_id = int(cb.data.split(":")[1])
    st = await state.get_data()
    st["actors"] = [actor_id]
    await state.set_data(st)
    await cb.answer()
    await _show_actors(cb.message, state, session, exclude=[actor_id], second=True)


@generate_router.callback_query(GenStates.actor2, F.data.startswith("act:"))
async def actor2_chosen(cb: CallbackQuery, state: FSMContext, session):
    actor_id = int(cb.data.split(":")[1])
    st = await state.get_data()
    if actor_id not in st["actors"]:
        st["actors"].append(actor_id)
    await state.set_data(st)
    await cb.answer()
    await _show_scenes(cb.message, state, session)


@generate_router.callback_query(GenStates.actor2, F.data == "a2:no")
async def actor2_skip(cb: CallbackQuery, state: FSMContext, session):
    await cb.answer()
    await _show_scenes(cb.message, state, session)


async def _ask_detail(target: Message, state: FSMContext):
    await state.set_state(GenStates.detail)
    await target.answer(texts.ASK_DETAIL, reply_markup=keyboards.grid([(texts.BTN_SKIP, "detail:skip")], 1, [keyboards.cancel_row()]))


# Тоже раньше scene:<id>: "scene:page:1" не должно уйти в выбор сцены.
@generate_router.callback_query(GenStates.scene, F.data.startswith("scene:page:"))
async def scenes_page(cb: CallbackQuery, state: FSMContext, session):
    await cb.answer()
    await _show_scenes(cb.message, state, session, page=int(cb.data.rsplit(":", 1)[1]))


@generate_router.callback_query(GenStates.scene, F.data == "scene:custom")
async def scene_custom(cb: CallbackQuery, state: FSMContext):
    await state.set_state(GenStates.custom_scene)
    await cb.answer()
    await cb.message.answer(texts.CUSTOM_SCENE_PROMPT)


@generate_router.callback_query(GenStates.scene, F.data.startswith("scene:"))
async def scene_chosen(cb: CallbackQuery, state: FSMContext):
    st = await state.get_data()
    st.update(scene_id=int(cb.data.split(":")[1]), custom_text=None, custom_file_id=None)
    await state.set_data(st)
    await cb.answer()
    await _ask_detail(cb.message, state)


@generate_router.message(GenStates.custom_scene, F.photo | F.document)
async def custom_scene_photo(message: Message, state: FSMContext):
    file_id = _photo_file_id(message)
    if not file_id:
        await message.answer(texts.NOT_A_PHOTO)
        return
    st = await state.get_data()
    st.update(scene_id=None, custom_text=None, custom_file_id=file_id)
    await state.set_data(st)
    await _ask_detail(message, state)


@generate_router.message(GenStates.custom_scene, F.text)
async def custom_scene_text(message: Message, state: FSMContext):
    err = validate_custom_scene(message.text)
    if err:
        await message.answer(err)
        return
    st = await state.get_data()
    st.update(scene_id=None, custom_text=message.text.strip(), custom_file_id=None)
    await state.set_data(st)
    await _ask_detail(message, state)


async def _ask_model(target: Message, state: FSMContext, user, settings):
    await state.set_state(GenStates.model)
    items = [(texts.MODEL_BASE_BTN.format(cost=settings.cost_base), "model:base")]
    text = texts.CHOOSE_MODEL
    if subscriptions.is_active(user):
        items.append((texts.MODEL_PREMIUM_BTN.format(cost=settings.cost_premium), "model:premium"))
    else:
        text += "\n" + texts.MODEL_PREMIUM_LOCKED
    await target.answer(text, reply_markup=keyboards.grid(items, 1, [keyboards.cancel_row()]))


@generate_router.callback_query(GenStates.detail, F.data == "detail:skip")
async def detail_skip(cb: CallbackQuery, state: FSMContext, user, settings):
    st = await state.get_data()
    st["detail"] = None
    await state.set_data(st)
    await cb.answer()
    await _ask_model(cb.message, state, user, settings)


@generate_router.message(GenStates.detail, F.text)
async def detail_text(message: Message, state: FSMContext, user, settings):
    err = validate_detail(message.text)
    if err:
        await message.answer(err)
        return
    st = await state.get_data()
    st["detail"] = message.text.strip()
    await state.set_data(st)
    await _ask_model(message, state, user, settings)


async def _show_confirm(target: Message, state: FSMContext, session, user, settings):
    st = await state.get_data()
    tier = st["tier"]
    if tier == "premium" and not subscriptions.is_active(user):
        tier = st["tier"] = "base"
        await state.set_data(st)
    cost = settings.cost_premium if tier == "premium" else settings.cost_base
    actors = [a for a in [await catalog.get_actor(session, i) for i in st["actors"]] if a]
    scene = await catalog.get_scene(session, st["scene_id"]) if st.get("scene_id") else None
    text = summary(st, [a.name for a in actors], scene_label(st, scene.name if scene else None), tier, cost, user.crystals)
    await state.set_state(GenStates.confirm)
    await target.answer(text, reply_markup=keyboards.grid([(texts.BTN_GENERATE, "gen:go")], 1, [keyboards.cancel_row()]))


@generate_router.callback_query(GenStates.model, F.data.startswith("model:"))
async def model_chosen(cb: CallbackQuery, state: FSMContext, session, user, settings):
    st = await state.get_data()
    st["tier"] = cb.data.split(":")[1]
    await state.set_data(st)
    await cb.answer()
    await _show_confirm(cb.message, state, session, user, settings)


async def send_result_photo(target: Message, image: bytes, caption: str, attempts: int = 2):
    """Отправка результата с одним повтором. Кристаллики не возвращаются (спек §7):
    генерация удалась, результат лежит в базе."""
    for attempt in range(1, attempts + 1):
        try:
            return await target.answer_photo(
                BufferedInputFile(image, "photo.jpg"), caption=caption, reply_markup=keyboards.result_kb()
            )
        except Exception as e:
            logger.warning("send result photo failed (attempt {}/{}): {}", attempt, attempts, e)
            if attempt < attempts:
                await asyncio.sleep(1)
    logger.error("result photo not delivered after {} attempts", attempts)
    return None


async def _run_generation(target: Message, state: FSMContext, session, user, settings, generator):
    st = await state.get_data()
    if not is_complete(st):
        await state.clear()
        await target.answer(texts.SESSION_EXPIRED, reply_markup=keyboards.main_menu())
        return
    tier = st.get("tier", "base")
    if tier == "premium" and not subscriptions.is_active(user):
        tier = "base"
        st["tier"] = tier
        await state.set_data(st)
    cost = settings.cost_premium if tier == "premium" else settings.cost_base
    if user.crystals < cost:
        await target.answer(texts.NOT_ENOUGH.format(cost=cost, balance=user.crystals))
        return
    await session.commit()  # release our row before generator opens its own sessions
    wait_msg = await target.answer(texts.GENERATING)
    try:
        outcome = await generator.run(request_from_state(user.id, st, tier))
    except AlreadyRunning:
        await wait_msg.edit_text(texts.ALREADY_RUNNING)
        return
    except wallet.InsufficientCrystals as e:
        await wait_msg.edit_text(texts.NOT_ENOUGH.format(cost=e.needed, balance=e.balance))
        return
    await session.refresh(user)
    if outcome.status == "done":
        actors = [a.name for a in [await catalog.get_actor(session, i) for i in st["actors"]] if a]
        scene = await catalog.get_scene(session, st["scene_id"]) if st.get("scene_id") else None
        caption = texts.RESULT_CAPTION.format(actors=", ".join(actors), scene=scene_label(st, scene.name if scene else None))
        sent = await send_result_photo(target, outcome.image_bytes, caption)
        if sent is None:
            await wait_msg.edit_text(texts.RESULT_SEND_FAILED)
            return
        gen = await session.get(Generation, outcome.generation_id)
        if gen and sent.photo:
            gen.result_file_id = sent.photo[-1].file_id
        await wait_msg.delete()
        try:
            await send_bonus_card(target.bot, user.id, user, settings)
        except Exception as e:
            logger.warning("bonus card send failed: {}", e)
    elif outcome.status == "rejected":
        await wait_msg.edit_text(texts.GEN_REJECTED)
    else:
        await wait_msg.edit_text(texts.GEN_FAILED)


@generate_router.callback_query(GenStates.confirm, F.data == "gen:go")
@generate_router.callback_query(GenStates.confirm, F.data == "gen:more")
async def gen_go(cb: CallbackQuery, state: FSMContext, session, user, settings, generator):
    await cb.answer()
    await _run_generation(cb.message, state, session, user, settings, generator)


@generate_router.callback_query(F.data == "gen:change_scene")
async def gen_change_scene(cb: CallbackQuery, state: FSMContext, session):
    await cb.answer()
    st = await state.get_data()
    if not st.get("people"):
        await cb.message.answer(texts.SESSION_EXPIRED, reply_markup=keyboards.main_menu())
        return
    await _show_scenes(cb.message, state, session)


@generate_router.callback_query(F.data == "gen:change_actor")
async def gen_change_actor(cb: CallbackQuery, state: FSMContext, session):
    await cb.answer()
    st = await state.get_data()
    if not st.get("people"):
        await cb.message.answer(texts.SESSION_EXPIRED, reply_markup=keyboards.main_menu())
        return
    st["actors"] = []
    await state.set_data(st)
    await _show_actors(cb.message, state, session)


@generate_router.callback_query(F.data == "gen:new")
async def gen_new(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await _start_flow(cb.message, state)


# Регистрируется после варианта в состоянии confirm: ловит «Ещё вариант»,
# когда FSM уже протухла по TTL.
@generate_router.callback_query(F.data == "gen:more")
async def gen_more_expired(cb: CallbackQuery):
    await cb.answer(texts.SESSION_EXPIRED, show_alert=True)
