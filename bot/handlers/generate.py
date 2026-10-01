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
    apply_catalog_scene,
    apply_custom_scene,
    effective_tier,
    empty_data,
    is_complete,
    paginate,
    request_from_state,
    scene_label,
    validate_custom_scene,
    validate_detail,
)
from bot.intro import send_intro
from database.models import Generation
from services import catalog
from services.billing import wallet
from services.generation import faces
from services.generation import generator as gen_service
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
    await message.answer(
        texts.SEND_PERSON_1,
        reply_markup=keyboards.grid([], extra_rows=[keyboards.back_row("menu"), keyboards.cancel_row()]),
    )


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
    if mode != "add":
        # «Свой герой» нельзя мешать с добором второго актёра из каталога.
        extra.append([(texts.BTN_HERO, "act:hero")])
    extra.append(keyboards.back_row("photo"))
    extra.append(keyboards.cancel_row())
    st = await state.get_data()
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
    st = await state.get_data()
    extra.append(keyboards.back_row("result" if is_complete(st) else "actors"))
    extra.append(keyboards.cancel_row())
    await state.set_state(GenStates.scene)
    await target.answer(texts.CHOOSE_SCENE, reply_markup=keyboards.grid(items, 2, extra))


async def _drop_edit(state: FSMContext, st: dict) -> dict:
    """Снимает одноразовые флаги правки детали: любая другая кнопка под
    результатом — обычная генерация."""
    had = "edit_mode" in st or "edit_base_id" in st
    st.pop("edit_mode", None)
    st.pop("edit_base_id", None)
    if had:
        await state.set_data(st)
    return st


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


async def _ask_hero(target: Message, state: FSMContext):
    await state.set_state(GenStates.hero)
    await target.answer(
        texts.SEND_HERO,
        reply_markup=keyboards.grid([], extra_rows=[keyboards.back_row("actors"), keyboards.cancel_row()]),
    )


@generate_router.message(GenStates.hero, F.photo | F.document)
async def got_hero_photo(message: Message, state: FSMContext, session, bot: Bot, user, settings, generator):
    """«Свой герой»: одно фото любого человека вместо актёра из каталога."""
    file_id = _photo_file_id(message)
    if not file_id:
        await message.answer(texts.NOT_A_PHOTO)
        return
    data = (await bot.download(file_id)).read()
    if not await asyncio.to_thread(faces.has_face, data):
        await message.answer(texts.NO_FACE)
        return
    st = await state.get_data()
    st["hero_file_id"] = file_id
    st["actors"] = []
    if not (st.get("scene_id") or st.get("custom_text") or st.get("custom_file_id")):
        # Быстрый флоу: сцену выбираем сами, пользователь поменяет её кнопкой.
        scenes = await catalog.list_scenes(session)
        if not scenes:
            await state.clear()
            await message.answer(texts.CATALOG_EMPTY, reply_markup=keyboards.main_menu())
            return
        st.update(scene_id=random.choice(scenes).id, custom_text=None, custom_file_id=None)
    await state.set_data(st)
    await _run_generation(message, state, session, user, settings, generator)


@generate_router.message(GenStates.person1)
@generate_router.message(GenStates.hero)
async def not_a_photo(message: Message):
    await message.answer(texts.NOT_A_PHOTO)


# Зарегистрирован раньше act:<id>: "act:hero" не должно уйти в выбор актёра.
@generate_router.callback_query(GenStates.actor1, F.data == "act:hero")
async def act_hero(cb: CallbackQuery, state: FSMContext):
    st = await state.get_data()
    st.pop("_pick_mode", None)
    await state.set_data(st)
    await cb.answer()
    await _ask_hero(cb.message, state)


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
        # Обычный выбор и «Другой актёр» сбрасывают «своего героя».
        st["actors"] = [actor_id]
        st["hero_file_id"] = None
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
    await target.answer(
        texts.ASK_DETAIL,
        reply_markup=keyboards.grid([], extra_rows=[keyboards.back_row("result"), keyboards.cancel_row()]),
    )


# Тоже раньше scene:<id>: "scene:page:1" не должно уйти в выбор сцены.
@generate_router.callback_query(GenStates.scene, F.data.startswith("scene:page:"))
async def scenes_page(cb: CallbackQuery, state: FSMContext, session):
    await cb.answer()
    await _show_scenes(cb.message, state, session, page=int(cb.data.rsplit(":", 1)[1]))


@generate_router.callback_query(GenStates.scene, F.data == "scene:custom")
async def scene_custom(cb: CallbackQuery, state: FSMContext):
    await state.set_state(GenStates.custom_scene)
    await cb.answer()
    await cb.message.answer(
        texts.CUSTOM_SCENE_PROMPT,
        reply_markup=keyboards.grid([], extra_rows=[keyboards.back_row("scenes"), keyboards.cancel_row()]),
    )


@generate_router.callback_query(GenStates.scene, F.data.startswith("scene:"))
async def scene_chosen(cb: CallbackQuery, state: FSMContext, session, user, settings, generator):
    st = apply_catalog_scene(await state.get_data(), int(cb.data.split(":")[1]))
    await state.set_data(st)
    await cb.answer()
    await _run_generation(cb.message, state, session, user, settings, generator)


@generate_router.message(GenStates.custom_scene, F.photo | F.document)
async def custom_scene_photo(message: Message, state: FSMContext, session, user, settings, generator):
    file_id = _photo_file_id(message)
    if not file_id:
        await message.answer(texts.NOT_A_PHOTO)
        return
    st = apply_custom_scene(await state.get_data(), file_id=file_id)
    await state.set_data(st)
    await _run_generation(message, state, session, user, settings, generator)


@generate_router.message(GenStates.custom_scene, F.text)
async def custom_scene_text(message: Message, state: FSMContext, session, user, settings, generator):
    err = validate_custom_scene(message.text)
    if err:
        await message.answer(err)
        return
    st = apply_custom_scene(await state.get_data(), text=message.text.strip())
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
    req = request_from_state(user.id, st, tier)
    # Правка детали одноразовая: следующая кнопка снова даёт обычную генерацию.
    had_edit = st.pop("edit_mode", None)
    st.pop("edit_base_id", None)
    if had_edit:
        await state.set_data(st)
    await session.commit()  # release our row before generator opens its own sessions
    wait_msg = await target.answer(texts.GENERATING)
    try:
        outcome = await generator.run(req)
    except AlreadyRunning:
        await wait_msg.edit_text(texts.ALREADY_RUNNING)
        return
    except wallet.InsufficientCrystals as e:
        await wait_msg.edit_text(f"{texts.NOT_ENOUGH.format(cost=e.needed, balance=e.balance)}\n\n{texts.NOT_ENOUGH_HINT}")
        return
    await session.refresh(user)
    await state.set_state(GenStates.result)
    if outcome.status == "done":
        if st.get("hero_file_id"):
            actors = [texts.HERO_LABEL]
        else:
            actors = [a.name for a in [await catalog.get_actor(session, i) for i in st["actors"]] if a]
        scene = await catalog.get_scene(session, st["scene_id"]) if st.get("scene_id") else None
        caption = texts.RESULT_CAPTION.format(actors=", ".join(actors), scene=scene_label(st, scene.name if scene else None))
        # Кнопке «Скачать в HD» нужен id генерации, «Своей детали» — сид кадра.
        st["last_generation_id"] = outcome.generation_id
        st["last_seed"] = outcome.seed
        await state.set_data(st)
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
    # Новая фотосессия — именно новая: без правки поверх кадра и с новым сидом.
    st = await _drop_edit(state, st)
    st["last_seed"] = None
    await state.set_data(st)
    await cb.answer()
    await _run_generation(cb.message, state, session, user, settings, generator)


@generate_router.callback_query(F.data == "gen:change_scene")
async def gen_change_scene(cb: CallbackQuery, state: FSMContext, session):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    # Сцена меняется — править прежний кадр бессмысленно.
    await _drop_edit(state, st)
    await cb.answer()
    await _show_scenes(cb.message, state, session)


@generate_router.callback_query(F.data == "gen:change_actor")
async def gen_change_actor(cb: CallbackQuery, state: FSMContext, session):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    # Актёр меняется — править прежний кадр бессмысленно.
    await _drop_edit(state, st)
    await cb.answer()
    await _show_actors(cb.message, state, session, mode="change")


@generate_router.callback_query(F.data == "gen:add_actor")
async def gen_add_actor(cb: CallbackQuery, state: FSMContext, session):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    if st.get("hero_file_id") or len(st.get("actors", [])) != 1:
        await cb.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    await cb.answer()
    await _show_actors(cb.message, state, session, exclude=st.get("actors"), mode="add")


@generate_router.callback_query(F.data.startswith("gen:hd:"))
async def gen_hd(cb: CallbackQuery, session, user):
    """Оригинал с Runware файлом-документом: без сжатия Telegram."""
    gen = await session.get(Generation, int(cb.data.rsplit(":", 1)[1]))
    if gen is None or gen.user_id != user.id or not gen.result_url:
        await cb.answer(texts.HD_EXPIRED, show_alert=True)
        return
    await cb.answer()
    try:
        data = await gen_service.download_bytes(gen.result_url)
    except Exception as e:
        # Ссылки Runware протухают примерно через 7 дней.
        logger.warning("hd download failed for generation {}: {}", gen.id, e)
        await cb.message.answer(texts.HD_EXPIRED)
        return
    await cb.message.answer_document(BufferedInputFile(data, "photo_hd.jpg"))


@generate_router.callback_query(F.data == "gen:detail")
async def gen_ask_detail(cb: CallbackQuery, state: FSMContext):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    # Деталь дорисовываем на том же кадре: генератор возьмёт его как первый
    # референс и тот же сид. Без id предыдущей генерации — обычная генерация.
    st["edit_mode"] = True
    st["edit_base_id"] = st.get("last_generation_id")
    await state.set_data(st)
    await cb.answer()
    await _ask_detail(cb.message, state)


@generate_router.callback_query(F.data == "gen:new")
async def gen_new(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await start_create_flow(cb.message, state)


@generate_router.callback_query(F.data.startswith("nav:back:"))
async def nav_back(cb: CallbackQuery, state: FSMContext, session, user, settings):
    """Шаг назад с явной целью: истории переходов не держим."""
    target = cb.data.rsplit(":", 1)[1]
    await cb.answer()
    if target == "menu":
        await state.clear()
        await send_intro(cb.bot, user.id, settings.webapp_url)
        return
    if target == "photo":
        await start_create_flow(cb.message, state)
        return
    if target == "scenes":
        await _show_scenes(cb.message, state, session)
        return
    if target == "result":
        st = await _drop_edit(state, await state.get_data())
        if is_complete(st):
            await state.set_state(GenStates.result)
            await cb.message.answer(texts.BACK_TO_RESULT, reply_markup=keyboards.result_kb(st))
            return
    st = await state.get_data()
    st.pop("_pick_mode", None)
    await state.set_data(st)
    await _show_actors(cb.message, state, session)
