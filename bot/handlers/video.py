"""Оживление готового кадра: само, кнопки действий или свой текст."""
import asyncio
from io import BytesIO
from uuid import uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from loguru import logger

from bot import keyboards, texts
from bot.flow import GenStates, validate_video_prompt
from bot.handlers.generate import _answer_not_enough
from database.models import Generation
from services.billing import subscriptions, wallet
from services.generation import watermark
from services.generation import generator as gen_service
from services.video.prompts import ACTIONS, video_prompt
from services.video.replicate_client import ReplicateVideo, VideoError

video_router = Router(name="video")

_running: set[int] = set()


def _parse_generation_id(data: str) -> int | None:
    raw = data.rsplit(":", 1)[-1]
    if not raw.isdigit():
        return None
    return int(raw)


async def _frame_bytes(bot, gen: Generation, user) -> bytes:
    """Берём уже отправленное фото: у бесплатных на нём есть знак. Иначе оригинал и тот же знак."""
    if gen.result_file_id:
        buf = BytesIO()
        await bot.download(gen.result_file_id, destination=buf)
        return buf.getvalue()
    if not gen.result_url:
        return b""
    data = await gen_service.download_bytes(gen.result_url)
    if data and not subscriptions.is_active(user):
        return await asyncio.to_thread(watermark.apply_free_mark, data)
    return data


async def _run(
    target: Message,
    session,
    user,
    settings,
    gen: Generation,
    action: str,
    custom: str | None,
    *,
    client=None,
) -> None:
    if user.id in _running:
        await target.answer(texts.ALREADY_RUNNING)
        return
    cost = settings.cost_video
    if user.crystals < cost:
        await _answer_not_enough(target, user, settings, cost)
        return
    try:
        frame = await _frame_bytes(target.bot, gen, user)
    except Exception as e:
        logger.warning("video frame download failed for {}: {}", gen.id, e)
        await target.answer(texts.VIDEO_NO_FRAME)
        return
    if not frame:
        await target.answer(texts.VIDEO_NO_FRAME)
        return
    ref = f"{gen.id}:{uuid4().hex[:8]}"
    _running.add(user.id)
    try:
        try:
            await wallet.charge_video(session, user.id, cost, ref)
            await session.commit()
        except wallet.InsufficientCrystals as e:
            await _answer_not_enough(target, user, settings, e.needed)
            return
        wait = await target.answer(texts.VIDEO_WAIT)
        animator = client or ReplicateVideo(
            settings.replicate_api_token, settings.video_model, settings.video_timeout_sec,
        )
        try:
            video = await animator.animate(
                frame,
                video_prompt(action, custom),
                seconds=settings.video_seconds,
                resolution=settings.video_resolution,
            )
        except (VideoError, Exception) as e:
            logger.warning("video failed for user {} gen {}: {}", user.id, gen.id, type(e).__name__)
            await wallet.refund_video(session, user.id, ref)
            await session.commit()
            await wait.edit_text(texts.VIDEO_FAILED)
            return
        await session.refresh(user)
        caption = texts.VIDEO_CAPTION.format(seconds=settings.video_seconds)
        notice = texts.CHARGED.format(cost=cost, word=texts.crystals_word(cost), balance=user.crystals)
        try:
            await target.answer_video(BufferedInputFile(video, "video.mp4"), caption=caption)
            await wait.edit_text(notice)
        except Exception as e:
            logger.warning("video send failed for {}: {}", user.id, e)
            await wallet.refund_video(session, user.id, ref)
            await session.commit()
            await wait.edit_text(texts.VIDEO_FAILED)
    finally:
        _running.discard(user.id)


async def _generation(session, user, generation_id: int) -> Generation | None:
    gen = await session.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id or gen.status != "done":
        return None
    if not gen.result_file_id and not gen.result_url:
        return None
    return gen


@video_router.callback_query(F.data == "gen:video:cancel")
async def cancel_video(cb: CallbackQuery, state: FSMContext):
    await state.set_state(GenStates.result)
    await cb.answer()
    await cb.message.edit_text(texts.CANCELLED)


@video_router.callback_query(F.data.startswith("gen:video:"))
async def open_video_menu(cb: CallbackQuery, state: FSMContext, session, user, settings):
    if not (settings.replicate_api_token or "").strip():
        await cb.answer(texts.VIDEO_NOT_READY, show_alert=True)
        return
    generation_id = _parse_generation_id(cb.data)
    gen = await _generation(session, user, generation_id) if generation_id else None
    if gen is None:
        await cb.answer(texts.VIDEO_NO_FRAME, show_alert=True)
        return
    await state.set_state(GenStates.result)
    await state.update_data(video_generation_id=gen.id)
    await cb.answer()
    await cb.message.answer(
        texts.VIDEO_MENU.format(seconds=settings.video_seconds, n=settings.cost_video),
        reply_markup=keyboards.video_menu_kb(gen.id),
    )


@video_router.callback_query(F.data.startswith("gen:v:"))
async def pick_video_action(cb: CallbackQuery, state: FSMContext, session, user, settings):
    parts = cb.data.split(":")
    # gen:v:<action>:<id>
    if len(parts) != 4:
        await cb.answer(texts.VIDEO_NO_FRAME, show_alert=True)
        return
    action, generation_id = parts[2], _parse_generation_id(cb.data)
    gen = await _generation(session, user, generation_id) if generation_id else None
    if gen is None or (action != "custom" and action not in ACTIONS):
        await cb.answer(texts.VIDEO_NO_FRAME, show_alert=True)
        return
    if action == "custom":
        await state.set_state(GenStates.video_prompt)
        await state.update_data(video_generation_id=gen.id)
        await cb.answer()
        await cb.message.answer(texts.VIDEO_ASK)
        return
    await cb.answer()
    await _run(cb.message, session, user, settings, gen, action, None)


@video_router.message(GenStates.video_prompt, F.text)
async def video_custom_text(message: Message, state: FSMContext, session, user, settings):
    err = validate_video_prompt(message.text)
    if err:
        await message.answer(err)
        return
    data = await state.get_data()
    gen = await _generation(session, user, data.get("video_generation_id") or 0)
    if gen is None:
        await state.set_state(GenStates.result)
        await message.answer(texts.VIDEO_NO_FRAME)
        return
    await state.set_state(GenStates.result)
    await _run(message, session, user, settings, gen, "custom", message.text.strip())


@video_router.message(GenStates.video_prompt)
async def video_custom_not_text(message: Message):
    await message.answer(texts.VIDEO_PROMPT_EMPTY)
