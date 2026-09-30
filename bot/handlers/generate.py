import asyncio
import random

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
    effective_tier,
    empty_data,
    is_complete,
    paginate,
    request_from_state,
    scene_label,
    validate_custom_scene,
    validate_detail,
)
from database.models import Generation
from services import catalog
from services.billing import wallet
from services.generation import faces
from services.generation.generator import AlreadyRunning

generate_router = Router(name="generate")


def _photo_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document.file_id
    return None


async def start_create_flow(message: Message, state: FSMContext):
    await state.clear()
    await state.set_data(empty_data())
    await state.set_state(GenStates.person1)
    await message.answer(texts.SEND_PERSON_1, reply_markup=keyboards.grid([], extra_rows=[keyboards.cancel_row()]))


@generate_router.message(F.text == texts.BTN_CREATE)
async def btn_create(message: Message, state: FSMContext):
    await start_create_flow(message, state)


@generate_router.callback_query(F.data == "menu:create")
async def cb_create(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await start_create_flow(cb.message, state)


def _nav_row(prefix: str, page: int, has_prev: bool, has_next: bool) -> list[list[tuple[str, str]]]:
    row = []
    if has_prev:
        row.append((texts.BTN_PREV, f"{prefix}:page:{page - 1}"))
    if has_next:
        row.append((texts.BTN_NEXT, f"{prefix}:page:{page + 1}"))
    return [row] if row else []


async def _show_actors(
    target: Message, state: FSMContext, session,
    exclude: list[int] | None = None, page: int = 0, mode: str | None = None,
):
    """Показывает список актёров в состоянии actor1.

    `mode` определяет, что делать при выборе актёра (см. actor1_chosen):
    None — обычный первый выбор (случайная сцена, сразу генерация),
    "add" — добираем второго актёра (кнопка «Ещё актёр» под результатом),
    "change" — заменяем актёра целиком (кнопка «Другой актёр» под результатом).
    """
    all_actors = await catalog.list_actors(session)
    if not all_actors:
        await state.clear()
        await target.answer(texts.CATALOG_EMPTY, reply_markup=keyboards.main_menu())
        return
    actors = [a for a in all_actors if a.id not in (exclude or [])]
    chunk, has_prev, has_next = paginate(actors, page, ACTORS_PER_PAGE)
    items = [(a.name, f"act:{a.id}") for a in chunk]
    extra = _nav_row("act", page, has_prev, has_next)
    st = await state.get_data()
    if mode is None and len(st.get("people", [])) < 2:
        extra.append([(texts.BTN_ADD_PERSON, "act:addperson")])
    extra.append(keyboards.cancel_row())
    if mode is not None:
        st["_pick_mode"] = mode
        await state.set_data(st)
    await state.set_state(GenStates.actor1)
    text = texts.CHOOSE_ACTOR_2 if mode == "add" else texts.CHOOSE_ACTOR
    await target.answer(text, reply_markup=keyboards.grid(items, 2, extra))


async def _show_scenes(target: Message, state: FSMContext, session, page: int = 0):
    scenes = await catalog.list_scenes(session)
    chunk, has_prev, has_next = paginate(scenes, page, SCENES_PER_PAGE)
    items = [(s.name, f"scene:{s.id}") for s in chunk]
    extra = _nav_row("scene", page, has_prev, has_next)
    extra.append([(texts.BTN_CUSTOM_SCENE, "scene:custom")])
    extra.append(keyboards.cancel_row())
    await state.set_state(GenStates.scene)
    await target.answer(texts.CHOOSE_SCENE, reply_markup=keyboards.grid(items, 2, extra))


async def _check_result_session(cb: CallbackQuery, state: FSMContext) -> dict | None:
    """Общая проверка для кнопок под результатом: если FSM-данные протухли
    (TTL стораджа или рестарт), отвечаем алертом вместо запуска генерации."""
    st = await state.get_data()
    if not is_complete(st):
        await cb.answer(texts.SESSION_EXPIRED, show_alert=True)
        return None
    return st


@generate_router.message(GenStates.person1, F.photo | F.document)
async def got_person1_photo(message: Message, state: FSMContext, session, bot: Bot):
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


@generate_router.message(GenStates.person2, F.photo | F.document)
async def got_person2_photo(message: Message, state: FSMContext, session, bot: Bot, user, settings, generator):
    file_id = _photo_file_id(message)
    if not file_id:
        await message.answer(texts.NOT_A_PHOTO)
        return
    data = (await bot.download(file_id)).read()
    if not await asyncio.to_thread(faces.has_face, data):
        await message.answer(texts.NO_FACE)
        return
    st = await state.get_data()
    st["people"].append(file_id)
    await state.set_data(st)
    if st.get("actors"):
        # Второй человек добавлен из «➕ Добавить человека» под результатом —
        # актёр и сцена уже выбраны, сразу генерируем.
        await _run_generation(message, state, session, user, settings, generator)
    else:
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
async def actors_page(cb: CallbackQuery, state: FSMContext, session):
    page = int(cb.data.rsplit(":", 1)[1])
    st = await state.get_data()
    mode = st.get("_pick_mode")
    exclude = st.get("actors") if mode == "add" else None
    await cb.answer()
    await _show_actors(cb.message, state, session, exclude=exclude, page=page, mode=mode)


@generate_router.callback_query(GenStates.actor1, F.data.startswith("act:"))
async def actor1_chosen(cb: CallbackQuery, state: FSMContext, session, user, settings, generator):
    actor_id = int(cb.data.split(":")[1])
    st = await state.get_data()
    mode = st.pop("_pick_mode", None)
    if mode == "add":
        actors = st.get("actors", [])
        if actor_id not in actors:
            actors.append(actor_id)
        st["actors"] = actors
    else:
        st["actors"] = [actor_id]
        if mode is None:
            # Первый выбор актёра в быстром флоу: сразу берём случайную активную
            # сцену и запускаем генерацию — без промежуточных вопросов.
            scenes = await catalog.list_scenes(session)
            if not scenes:
                await state.clear()
                await cb.answer()
                await cb.message.answer(texts.CATALOG_EMPTY, reply_markup=keyboards.main_menu())
                return
            scene = random.choice(scenes)
            st.update(scene_id=scene.id, custom_text=None, custom_file_id=None)
    await state.set_data(st)
    await cb.answer()
    await _run_generation(cb.message, state, session, user, settings, generator)


async def _ask_detail(target: Message, state: FSMContext):
    await state.set_state(GenStates.detail)
    await target.answer(texts.ASK_DETAIL, reply_markup=keyboards.grid([], extra_rows=[keyboards.cancel_row()]))


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
async def scene_chosen(cb: CallbackQuery, state: FSMContext, session, user, settings, generator):
    st = await state.get_data()
    st.update(scene_id=int(cb.data.split(":")[1]), custom_text=None, custom_file_id=None)
    await state.set_data(st)
    await cb.answer()
    await _run_generation(cb.message, state, session, user, settings, generator)


@generate_router.message(GenStates.custom_scene, F.photo | F.document)
async def custom_scene_photo(message: Message, state: FSMContext, session, user, settings, generator):
    file_id = _photo_file_id(message)
    if not file_id:
        await message.answer(texts.NOT_A_PHOTO)
        return
    st = await state.get_data()
    st.update(scene_id=None, custom_text=None, custom_file_id=file_id)
    await state.set_data(st)
    await _run_generation(message, state, session, user, settings, generator)


@generate_router.message(GenStates.custom_scene, F.text)
async def custom_scene_text(message: Message, state: FSMContext, session, user, settings, generator):
    err = validate_custom_scene(message.text)
    if err:
        await message.answer(err)
        return
    st = await state.get_data()
    st.update(scene_id=None, custom_text=message.text.strip(), custom_file_id=None)
    await state.set_data(st)
    await _run_generation(message, state, session, user, settings, generator)


@generate_router.message(GenStates.detail, F.text)
async def detail_text(message: Message, state: FSMContext, session, user, settings, generator):
    err = validate_detail(message.text)
    if err:
        await message.answer(err)
        return
    st = await state.get_data()
    st["detail"] = message.text.strip()
    await state.set_data(st)
    await _run_generation(message, state, session, user, settings, generator)


async def send_result_photo(target: Message, image: bytes, caption: str, data: dict, attempts: int = 2):
    """Отправка результата с одним повтором. Кристаллики не возвращаются (спек §7):
    генерация удалась, результат лежит в базе."""
    for attempt in range(1, attempts + 1):
        try:
            return await target.answer_photo(
                BufferedInputFile(image, "photo.jpg"), caption=caption, reply_markup=keyboards.result_kb(data)
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
    tier = effective_tier(user)
    cost = settings.cost_premium if tier == "premium" else settings.cost_base
    if user.crystals < cost:
        await target.answer(f"{texts.NOT_ENOUGH.format(cost=cost, balance=user.crystals)}\n\n{texts.NOT_ENOUGH_HINT}")
        return
    await session.commit()  # release our row before generator opens its own sessions
    wait_msg = await target.answer(texts.GENERATING)
    try:
        outcome = await generator.run(request_from_state(user.id, st, tier))
    except AlreadyRunning:
        await wait_msg.edit_text(texts.ALREADY_RUNNING)
        return
    except wallet.InsufficientCrystals as e:
        await wait_msg.edit_text(f"{texts.NOT_ENOUGH.format(cost=e.needed, balance=e.balance)}\n\n{texts.NOT_ENOUGH_HINT}")
        return
    await session.refresh(user)
    await state.set_state(GenStates.result)
    if outcome.status == "done":
        actors = [a.name for a in [await catalog.get_actor(session, i) for i in st["actors"]] if a]
        scene = await catalog.get_scene(session, st["scene_id"]) if st.get("scene_id") else None
        caption = texts.RESULT_CAPTION.format(actors=", ".join(actors), scene=scene_label(st, scene.name if scene else None))
        sent = await send_result_photo(target, outcome.image_bytes, caption, st)
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


@generate_router.callback_query(F.data == "gen:more")
async def gen_more(cb: CallbackQuery, state: FSMContext, session, user, settings, generator):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    await cb.answer()
    await _run_generation(cb.message, state, session, user, settings, generator)


@generate_router.callback_query(F.data == "gen:random_scene")
async def gen_random_scene(cb: CallbackQuery, state: FSMContext, session, user, settings, generator):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    scenes = await catalog.list_scenes(session)
    if not scenes:
        await cb.answer(texts.CATALOG_EMPTY, show_alert=True)
        return
    scene = random.choice(scenes)
    st.update(scene_id=scene.id, custom_text=None, custom_file_id=None)
    await state.set_data(st)
    await cb.answer()
    await _run_generation(cb.message, state, session, user, settings, generator)


@generate_router.callback_query(F.data == "gen:change_scene")
async def gen_change_scene(cb: CallbackQuery, state: FSMContext, session):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    await cb.answer()
    await _show_scenes(cb.message, state, session)


@generate_router.callback_query(F.data == "gen:change_actor")
async def gen_change_actor(cb: CallbackQuery, state: FSMContext, session):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    await cb.answer()
    await _show_actors(cb.message, state, session, mode="change")


@generate_router.callback_query(F.data == "gen:add_actor")
async def gen_add_actor(cb: CallbackQuery, state: FSMContext, session):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    if len(st.get("actors", [])) != 1:
        await cb.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    await cb.answer()
    await _show_actors(cb.message, state, session, exclude=st.get("actors"), mode="add")


@generate_router.callback_query(F.data == "gen:add_person")
async def gen_add_person(cb: CallbackQuery, state: FSMContext):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    if len(st.get("people", [])) != 1:
        await cb.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    await cb.answer()
    await state.set_state(GenStates.person2)
    await cb.message.answer(texts.SEND_PERSON_2)


@generate_router.callback_query(F.data == "gen:detail")
async def gen_ask_detail(cb: CallbackQuery, state: FSMContext):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    await cb.answer()
    await _ask_detail(cb.message, state)


@generate_router.callback_query(F.data == "gen:new")
async def gen_new(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await start_create_flow(cb.message, state)
