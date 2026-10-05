import asyncio

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from loguru import logger

from bot import keyboards, texts
from bot.bonus_card import send_bonus_card
from bot.flow import (
    ACTORS_PER_PAGE,
    SCENES_PER_PAGE,
    GenStates,
    add_person_buttons,
    apply_catalog_scene,
    apply_custom_scene,
    commit_pending,
    effective_tier,
    empty_data,
    is_complete,
    name_taken,
    norm_name,
    paginate,
    request_from_state,
    scene_label,
    validate_custom_scene,
    validate_detail,
)
from bot.intro import send_intro
from bot.refs_view import bot_username
from services import aliases
from services.channel_rank import level_title, published_count
from services.referrals import CHANNEL_CODE, link_for
from database.models import Generation
from services import catalog
from services.billing import bonus, subscriptions, wallet
from services.generation import faces
from services.generation import watermark
from services.generation import generator as gen_service
from services.generation.content_filter import is_allowed
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
    """Список актёров.

    mode None — первый актёр, дальше сцена.
    mode "insert" — вписать ещё одного в готовый кадр.
    """
    all_actors = await catalog.list_actors(session)
    st_now = await state.get_data()
    taken_names = {norm_name(item.get("name", "")) for item in st_now.get("named") or []}
    actors = [
        a for a in all_actors
        if a.id not in (exclude or []) and norm_name(a.name) not in taken_names
    ]
    chunk, has_prev, has_next = paginate(actors, page, ACTORS_PER_PAGE)
    items = [(a.name, f"act:{a.id}") for a in chunk]
    extra = _nav_row("act", page, has_prev, has_next)
    extra.append([(texts.BTN_WRITE_OWN, "act:write")])
    extra.append(keyboards.back_row("add" if mode == "insert" else "photo"))
    extra.append(keyboards.cancel_row())
    st = await state.get_data()
    if mode is not None:
        st["_pick_mode"] = mode
    else:
        st.pop("_pick_mode", None)
    await state.set_data(st)
    await state.set_state(GenStates.actor1)
    text = texts.CHOOSE_ACTOR_INSERT if mode == "insert" else texts.CHOOSE_ACTOR
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


async def _ask_actor_name(target: Message, state: FSMContext):
    await state.set_state(GenStates.actor_name)
    await target.answer(
        texts.ASK_ACTOR_NAME,
        reply_markup=keyboards.grid([], extra_rows=[keyboards.back_row("actors"), keyboards.cancel_row()]),
    )


async def _ask_actor_photos(target: Message, state: FSMContext, more: bool = False):
    await state.set_state(GenStates.actor_photos)
    await target.answer(
        texts.ASK_ACTOR_PHOTO_MORE if more else texts.ASK_ACTOR_PHOTOS,
        reply_markup=keyboards.grid(
            [],
            extra_rows=[[(texts.BTN_SKIP, "act:photos:skip")], keyboards.back_row("name"), keyboards.cancel_row()],
        ),
    )


async def _catalog_name_keys(session, actor_ids: list[int]) -> set[str]:
    keys = set()
    for aid in actor_ids:
        actor = await catalog.get_actor(session, aid)
        if actor:
            keys.add(norm_name(actor.name))
    return keys


@generate_router.message(GenStates.person1)
async def not_a_photo(message: Message):
    await message.answer(texts.NOT_A_PHOTO)


@generate_router.callback_query(GenStates.actor1, F.data == "act:write")
async def act_write(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await _ask_actor_name(cb.message, state)


@generate_router.message(GenStates.actor_name, F.text)
async def actor_name_text(message: Message, state: FSMContext, session):
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(texts.NAME_EMPTY)
        return
    if len(raw) > 64:
        await message.answer(texts.NAME_TOO_LONG)
        return
    if not is_allowed(raw):
        await message.answer(texts.TEXT_REJECTED)
        return
    st = await state.get_data()
    if name_taken(st, raw) or norm_name(raw) in await _catalog_name_keys(session, st.get("actors") or []):
        await message.answer(texts.ALREADY_ON_PHOTO)
        return
    st["pending_name"] = raw
    st["pending_files"] = []
    await state.set_data(st)
    await _ask_actor_photos(message, state)


@generate_router.message(GenStates.actor_photos, F.photo | F.document)
async def actor_photo(message: Message, state: FSMContext, session, bot: Bot, user, settings, generator):
    file_id = _photo_file_id(message)
    if not file_id:
        await message.answer(texts.NOT_A_PHOTO)
        return
    data = (await bot.download(file_id)).read()
    if not await asyncio.to_thread(faces.has_face, data):
        await message.answer(texts.NO_FACE)
        return
    st = await state.get_data()
    files = list(st.get("pending_files") or [])
    files.append(file_id)
    st["pending_files"] = files
    await state.set_data(st)
    if len(files) >= 2:
        await _finish_named_actor(message, state, session, user, settings, generator)
        return
    await _ask_actor_photos(message, state, more=True)


@generate_router.callback_query(GenStates.actor_photos, F.data == "act:photos:skip")
async def actor_photos_skip(cb: CallbackQuery, state: FSMContext, session, user, settings, generator):
    await cb.answer()
    await _finish_named_actor(cb.message, state, session, user, settings, generator)


@generate_router.message(GenStates.actor_name)
async def actor_name_not_text(message: Message):
    await message.answer(texts.NAME_EMPTY)


@generate_router.message(GenStates.actor_photos)
async def actor_photos_not_photo(message: Message):
    await message.answer(texts.NOT_A_PHOTO)


async def _finish_named_actor(target, state, session, user, settings, generator):
    st = await state.get_data()
    name = st.pop("pending_name", None)
    files = list(st.pop("pending_files", []) or [])
    mode = st.get("_pick_mode")
    if not name:
        await state.set_data(st)
        await _ask_actor_name(target, state)
        return
    if mode == "insert":
        st.pop("_pick_mode", None)
        st["pending_insert"] = {"kind": "named", "name": name, "files": files}
        await state.set_data(st)
        await _run_generation(target, state, session, user, settings, generator)
        return
    st.pop("_pick_mode", None)
    st["actors"] = []
    st["named"] = [{"name": name, "files": files}]
    st["base_actors"] = []
    st["base_named"] = [{"name": name, "files": list(files)}]
    await state.set_data(st)
    await _show_scenes(target, state, session)


# Зарегистрирован раньше act:<id>, иначе "act:page:2" попал бы в выбор актёра.
@generate_router.callback_query(GenStates.actor1, F.data.startswith("act:page:"))
async def actors_page(cb: CallbackQuery, state: FSMContext, session):
    page = int(cb.data.rsplit(":", 1)[1])
    st = await state.get_data()
    mode = st.get("_pick_mode")
    exclude = st.get("actors") if mode == "insert" else None
    await cb.answer()
    await _show_actors(cb.message, state, session, exclude=exclude, page=page, mode=mode)


@generate_router.callback_query(GenStates.actor1, F.data.startswith("act:"))
async def actor1_chosen(cb: CallbackQuery, state: FSMContext, session, user, settings, generator):
    actor_id = int(cb.data.split(":")[1])
    st = await state.get_data()
    mode = st.pop("_pick_mode", None)
    actor = await catalog.get_actor(session, actor_id)
    if actor is None:
        await cb.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    if mode == "insert":
        if actor_id in (st.get("actors") or []):
            await cb.answer(texts.ALREADY_ON_PHOTO, show_alert=True)
            return
        st["pending_insert"] = {"kind": "actor", "actor_id": actor_id, "name": actor.name}
        await state.set_data(st)
        await cb.answer()
        await _run_generation(cb.message, state, session, user, settings, generator)
        return
    st["actors"] = [actor_id]
    st["named"] = []
    st["base_actors"] = [actor_id]
    st["base_named"] = []
    await state.set_data(st)
    await cb.answer()
    await _show_scenes(cb.message, state, session)


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


async def _photo_for_user(image: bytes, user) -> bytes:
    """Без подписки на кадр ставится знак бота. Подписчик получает фото как есть."""
    if image and not subscriptions.is_active(user):
        return await asyncio.to_thread(watermark.apply_free_mark, image)
    return image


async def send_result_photo(
    target: Message, image: bytes, caption: str, data: dict, attempts: int = 2, *, publish: bool = False,
):
    """Отправка результата с одним повтором. Кристаллики не возвращаются (спек §7):
    генерация удалась, результат лежит в базе."""
    for attempt in range(1, attempts + 1):
        try:
            return await target.answer_photo(
                BufferedInputFile(image, "photo.jpg"),
                caption=caption,
                reply_markup=keyboards.result_kb(data, publish=publish),
            )
        except Exception as e:
            logger.warning("send result photo failed (attempt {}/{}): {}", attempt, attempts, e)
            if attempt < attempts:
                await asyncio.sleep(1)
    logger.error("result photo not delivered after {} attempts", attempts)
    return None


def _empty_balance_offer(user, settings) -> tuple[str, object]:
    """Если кристалликов не осталось: бонус, когда он уже доступен, иначе покупка."""
    if bonus.bonus_status(user, settings).ready:
        markup = keyboards.grid([(texts.BTN_BONUS_CLAIM, "bonus:claim")], 1)
        return texts.BALANCE_EMPTY_BONUS, markup
    markup = keyboards.grid(
        [(texts.BTN_BUY_PACK, "shop:packs"), (texts.BTN_BUY_SUB, "shop:subs")],
        1,
    )
    return texts.BALANCE_EMPTY_BUY, markup


def _with_empty_offer(text: str, user, settings) -> tuple[str, object | None]:
    if user.crystals > 0:
        return text, None
    extra, markup = _empty_balance_offer(user, settings)
    return f"{text}\n\n{extra}", markup


async def _answer_not_enough(target: Message, user, settings, cost: int) -> None:
    text, markup = _with_empty_offer(
        texts.NOT_ENOUGH.format(cost=cost, balance=user.crystals), user, settings
    )
    await target.answer(text, reply_markup=markup)


async def _run_generation(target: Message, state: FSMContext, session, user, settings, generator):
    st = await state.get_data()
    if not is_complete(st):
        await state.clear()
        await target.answer(texts.SESSION_EXPIRED, reply_markup=keyboards.main_menu())
        return
    tier = effective_tier(user)
    cost = settings.cost_premium if tier == "premium" else settings.cost_base
    if user.crystals < cost:
        st.pop("pending_insert", None)
        await state.set_data(st)
        await _answer_not_enough(target, user, settings, cost)
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
        await session.refresh(user)
        await wait_msg.delete()
        await _answer_not_enough(target, user, settings, e.needed)
        return
    await session.refresh(user)
    await state.set_state(GenStates.result)
    if outcome.status == "done":
        commit_pending(st)
        actors = [a.name for a in [await catalog.get_actor(session, i) for i in st.get("actors") or []] if a]
        actors += [item["name"] for item in st.get("named") or []]
        if st.get("self_file_id"):
            actors.append(texts.SELF_LABEL)
        scene = await catalog.get_scene(session, st["scene_id"]) if st.get("scene_id") else None
        caption = texts.RESULT_CAPTION.format(actors=", ".join(actors), scene=scene_label(st, scene.name if scene else None))
        # Кнопке «Скачать в HD» нужен id генерации, «Своей детали» — сид кадра.
        st["last_generation_id"] = outcome.generation_id
        st["last_seed"] = outcome.seed
        await state.set_data(st)
        notice = texts.CHARGED.format(cost=cost, word=texts.crystals_word(cost), balance=user.crystals)
        notice, markup = _with_empty_offer(notice, user, settings)
        await target.answer(notice, reply_markup=markup)
        photo = await _photo_for_user(outcome.image_bytes, user)
        sent = await send_result_photo(
            target, photo, caption, st, publish=settings.channel_chat() is not None,
        )
        if sent is None:
            await wait_msg.edit_text(texts.RESULT_SEND_FAILED)
            return
        gen = await session.get(Generation, outcome.generation_id)
        if gen and sent.photo:
            gen.result_file_id = sent.photo[-1].file_id
        await wait_msg.delete()
        if user.crystals > 0:
            try:
                await send_bonus_card(target.bot, user.id, user, settings)
            except Exception as e:
                logger.warning("bonus card send failed: {}", e)
    elif outcome.status == "rejected":
        st.pop("pending_insert", None)
        await state.set_data(st)
        await wait_msg.edit_text(texts.GEN_REJECTED)
    else:
        st.pop("pending_insert", None)
        await state.set_data(st)
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


async def _show_add_person(target: Message, state: FSMContext):
    st = await state.get_data()
    await state.set_state(GenStates.result)
    await target.answer(
        texts.ADD_PERSON,
        reply_markup=keyboards.grid(
            add_person_buttons(st),
            1,
            [keyboards.back_row("result"), keyboards.cancel_row()],
        ),
    )


@generate_router.callback_query(F.data == "gen:add_person")
async def gen_add_person(cb: CallbackQuery, state: FSMContext):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    if not st.get("last_generation_id"):
        await cb.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    await cb.answer()
    await _show_add_person(cb.message, state)


@generate_router.callback_query(F.data == "add:self")
async def add_self(cb: CallbackQuery, state: FSMContext):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    if st.get("self_file_id"):
        await cb.answer(texts.ALREADY_ON_PHOTO, show_alert=True)
        return
    await cb.answer()
    await state.set_state(GenStates.self_role)
    await cb.message.answer(
        texts.ASK_SELF_ROLE,
        reply_markup=keyboards.grid(
            [(texts.BTN_WATCH, "add:role:watch"), (texts.BTN_JOIN, "add:role:join")],
            2,
            [keyboards.back_row("add"), keyboards.cancel_row()],
        ),
    )


@generate_router.callback_query(GenStates.self_role, F.data.startswith("add:role:"))
async def add_self_role(cb: CallbackQuery, state: FSMContext):
    role = cb.data.rsplit(":", 1)[1]
    if role not in ("watch", "join"):
        await cb.answer()
        return
    st = await state.get_data()
    st["pending_role"] = role
    await state.set_data(st)
    await state.set_state(GenStates.self_photo)
    await cb.answer()
    await cb.message.answer(
        texts.ASK_SELF_PHOTO,
        reply_markup=keyboards.grid([], extra_rows=[keyboards.back_row("roles"), keyboards.cancel_row()]),
    )


@generate_router.message(GenStates.self_photo, F.photo | F.document)
async def got_self_photo(message: Message, state: FSMContext, session, bot: Bot, user, settings, generator):
    file_id = _photo_file_id(message)
    if not file_id:
        await message.answer(texts.NOT_A_PHOTO)
        return
    data = (await bot.download(file_id)).read()
    if not await asyncio.to_thread(faces.has_face, data):
        await message.answer(texts.NO_FACE)
        return
    st = await state.get_data()
    role = st.pop("pending_role", None)
    if role not in ("watch", "join") or not st.get("last_generation_id"):
        await state.set_data(st)
        await message.answer(texts.SESSION_EXPIRED)
        return
    st["pending_insert"] = {"kind": "self", "role": role, "file_id": file_id}
    await state.set_data(st)
    await _run_generation(message, state, session, user, settings, generator)


@generate_router.message(GenStates.self_photo)
async def self_photo_not_a_photo(message: Message):
    await message.answer(texts.NOT_A_PHOTO)


@generate_router.callback_query(F.data == "add:other")
async def add_other(cb: CallbackQuery, state: FSMContext, session):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    await cb.answer()
    await _show_actors(cb.message, state, session, exclude=st.get("actors"), mode="insert")


@generate_router.callback_query(F.data == "gen:publish")
async def gen_publish(cb: CallbackQuery, state: FSMContext, session, user, settings):
    st = await _check_result_session(cb, state)
    if st is None:
        return
    chat = settings.channel_chat()
    if chat is None:
        await cb.answer(texts.CHANNEL_NOT_READY, show_alert=True)
        return
    gen_id = st.get("last_generation_id")
    gen = await session.get(Generation, gen_id) if gen_id else None
    if gen is None or gen.user_id != user.id or gen.status != "done" or not gen.result_file_id:
        await cb.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    if gen.channel_message_id:
        await cb.answer(texts.CHANNEL_ALREADY, show_alert=True)
        return
    name = await aliases.assign_public_name(session, user)
    level = level_title(await published_count(session, user.id) + 1)
    username = await bot_username(cb.bot)
    markup = keyboards.channel_post_kb(link_for(username, CHANNEL_CODE))
    try:
        sent = await cb.bot.send_photo(
            chat,
            gen.result_file_id,
            caption=texts.CHANNEL_POST.format(name=name, level=level),
            reply_markup=markup,
        )
    except TelegramAPIError as e:
        logger.warning("channel publish failed for {}: {}", user.id, e)
        await cb.answer(texts.CHANNEL_FAILED, show_alert=True)
        return
    gen.channel_message_id = sent.message_id
    await cb.answer()
    await cb.message.answer(texts.CHANNEL_PUBLISHED.format(name=name, level=level))


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
    data = await _photo_for_user(data, user)
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
        await send_intro(cb.bot, user.id, settings.webapp_url, settings.channel_url)
        return
    if target == "photo":
        await start_create_flow(cb.message, state)
        return
    if target == "scenes":
        await _show_scenes(cb.message, state, session)
        return
    if target == "add":
        await _show_add_person(cb.message, state)
        return
    if target == "roles":
        await state.set_state(GenStates.self_role)
        await cb.message.answer(
            texts.ASK_SELF_ROLE,
            reply_markup=keyboards.grid(
                [(texts.BTN_WATCH, "add:role:watch"), (texts.BTN_JOIN, "add:role:join")],
                2,
                [keyboards.back_row("add"), keyboards.cancel_row()],
            ),
        )
        return
    if target == "name":
        await _ask_actor_name(cb.message, state)
        return
    if target == "result":
        st = await _drop_edit(state, await state.get_data())
        st.pop("pending_insert", None)
        st.pop("pending_role", None)
        await state.set_data(st)
        if is_complete(st):
            await state.set_state(GenStates.result)
            await cb.message.answer(
                texts.BACK_TO_RESULT,
                reply_markup=keyboards.result_kb(st, publish=settings.channel_chat() is not None),
            )
            return
    st = await state.get_data()
    mode = st.get("_pick_mode")
    await _show_actors(
        cb.message, state, session,
        exclude=st.get("actors") if mode == "insert" else None,
        mode=mode,
    )
