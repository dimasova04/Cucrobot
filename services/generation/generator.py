import asyncio
import base64
from collections import OrderedDict
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

import httpx
from loguru import logger
from sqlalchemy import select

from config.settings import Settings
from database.base import utcnow
from database.models import Generation
from services import catalog
from services.billing import wallet
from services.generation.prompt_builder import ActorInput, GenerationInput, build, build_edit
from services.generation.runware_client import ImageProvider, ImageResult, RunwareGenerationError


class AlreadyRunning(Exception):
    pass


# Имя, под которым «свой герой» попадает в Generation.actors. Подпись
# пользователю берётся из bot.texts.HERO_LABEL — сервисы не знают про тексты бота.
HERO_ACTOR_NAME = "свой герой"
# Нейтральная англоязычная метка для промпта: имени у героя нет.
HERO_PROMPT_NAME = "the second person"


@dataclass
class GenerationRequest:
    user_id: int
    people_file_ids: list[str]
    actor_ids: list[int]
    scene_id: int | None
    custom_scene_text: str | None
    custom_scene_file_id: str | None
    detail: str | None
    tier: str  # base / premium
    # «Свой герой»: одно фото вместо актёра из каталога. Взаимоисключающе с actor_ids.
    hero_file_id: str | None = None
    # Правка детали: дорисовываем на готовом кадре, а не генерим заново.
    base_generation_id: int | None = None
    edit_mode: bool = False


@dataclass
class GenerationOutcome:
    status: str  # done / failed / rejected
    generation_id: int
    image_bytes: bytes | None
    cost_usd: float | None
    error: str | None
    seed: int | None = None


class FileFetcher(Protocol):
    async def fetch(self, file_id: str) -> bytes: ...


class TelegramFileFetcher:
    def __init__(self, bot, cache_size: int = 200):
        self._bot = bot
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._size = cache_size

    async def fetch(self, file_id: str) -> bytes:
        if file_id in self._cache:
            self._cache.move_to_end(file_id)
            return self._cache[file_id]
        buf = await self._bot.download(file_id)
        data = buf.read()
        self._cache[file_id] = data
        if len(self._cache) > self._size:
            self._cache.popitem(last=False)
        return data


async def download_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


def _data_uri(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


class Generator:
    def __init__(self, session_factory, provider: ImageProvider, fetcher: FileFetcher, settings: Settings):
        self._sf = session_factory
        self._provider = provider
        self._fetcher = fetcher
        self._settings = settings
        self._running: set[int] = set()

    def _model(self, tier: str) -> tuple[str, int, int]:
        s = self._settings
        if tier == "premium":
            return s.model_premium_air, s.model_premium_max_refs, s.cost_premium
        return s.model_base_air, s.model_base_max_refs, s.cost_base

    async def run(self, req: GenerationRequest) -> GenerationOutcome:
        if req.user_id in self._running:
            raise AlreadyRunning()
        self._running.add(req.user_id)
        try:
            return await self._run(req)
        finally:
            self._running.discard(req.user_id)

    async def _run(self, req: GenerationRequest) -> GenerationOutcome:
        if not req.actor_ids and not req.hero_file_id:
            raise ValueError("request needs at least one actor id or a hero photo")
        model_air, max_refs, cost = self._model(req.tier)

        async with self._sf() as s:
            # Выключенный актёр — то же самое, что несуществующий: его могли
            # отключить, пока сессия пользователя висела в FSM.
            actors = [a for a in [await catalog.get_actor(s, i) for i in req.actor_ids] if a and a.is_active]
            if len(actors) != len(req.actor_ids):
                raise ValueError("unknown or inactive actor id")
            scene = await catalog.get_scene(s, req.scene_id) if req.scene_id else None
            if scene:
                scene_prompt, orientation, scene_ref_id, location = scene.prompt, scene.orientation, scene.ref_file_id, scene.name
            elif req.custom_scene_file_id:
                scene_prompt, orientation, scene_ref_id, location = "in the setting shown", "portrait", req.custom_scene_file_id, "custom:photo"
            else:
                scene_prompt, orientation, scene_ref_id, location = (req.custom_scene_text or ""), "portrait", None, "custom:text"

            base = await self._edit_base(s, req)

            balance = await wallet.get_balance(s, req.user_id)
            if balance < cost:
                raise wallet.InsufficientCrystals(needed=cost, balance=balance)
            actors_json = (
                [{"id": a.id, "name": a.name} for a in actors]
                if actors
                else [{"id": None, "name": HERO_ACTOR_NAME}]
            )
            gen = Generation(
                user_id=req.user_id, model_air=model_air, model_tier=req.tier,
                actors=actors_json,
                location=location, user_detail=req.detail, crystals_charged=cost,
            )
            s.add(gen)
            await s.flush()
            await wallet.charge_generation(s, req.user_id, cost, gen.id)
            await s.commit()
            gen_id = gen.id
            actor_inputs = [
                ActorInput(a.name, a.description, [r.file_id for r in a.refs]) for a in actors
            ] or [ActorInput(HERO_PROMPT_NAME, "", [req.hero_file_id])]

        try:
            people = [_data_uri(await self._fetcher.fetch(f)) for f in req.people_file_ids]
            for ai in actor_inputs:
                ai.refs = [_data_uri(await self._fetcher.fetch(f)) for f in ai.refs]
            scene_ref = _data_uri(await self._fetcher.fetch(scene_ref_id)) if scene_ref_id else None
            width, height = self._settings.frame_size(req.tier, orientation)
            inp = GenerationInput(people, actor_inputs, scene_prompt, scene_ref, req.detail, width, height)
            previous_image, seed = await self._load_base_image(base)
            if previous_image:
                prompt, refs = build_edit(inp, previous_image, req.detail or "", max_refs=max_refs)
            else:
                seed = None  # обычная генерация: каждый кадр со своим сидом
                prompt, refs = build(inp, max_refs=max_refs)
            result = await self._generate_with_retry(model_air, prompt, refs, width, height, seed)
            if result.nsfw:
                # Купальник и откровенная одежда сцены часто помечаются как nsfw.
                # Картинку всё равно отдаём: это и есть запрошенный кадр.
                logger.info("generation {} flagged nsfw by the provider, delivering the image", gen_id)
            image = await download_bytes(result.url)
            return await self._finish(
                gen_id, req.user_id, "done", image, result.cost, None, result.url,
                result.seed if result.seed is not None else seed,
            )
        except Exception as e:
            logger.exception("generation {} failed", gen_id)
            return await self._finish(gen_id, req.user_id, "failed", None, None, str(e))

    async def _edit_base(self, s, req: GenerationRequest) -> tuple[str, int | None] | None:
        """(ссылка на предыдущий кадр, его сид) — если правка детали применима."""
        if not (req.edit_mode and req.base_generation_id and req.detail):
            return None
        base = await s.get(Generation, req.base_generation_id)
        if base is None or base.user_id != req.user_id or base.status != "done" or not base.result_url:
            logger.warning(
                "edit base generation {} unusable for user {}: falling back to a fresh generation",
                req.base_generation_id, req.user_id,
            )
            return None
        return base.result_url, base.seed

    async def _load_base_image(self, base: tuple[str, int | None] | None) -> tuple[str | None, int | None]:
        """Качаем предыдущий кадр. Ссылки Runware протухают — если не вышло,
        молча делаем обычную генерацию вместо правки."""
        if base is None:
            return None, None
        url, seed = base
        try:
            return _data_uri(await download_bytes(url)), seed
        except Exception as e:
            logger.warning("edit base download failed ({}): falling back to a fresh generation", e)
            return None, None

    async def _generate_with_retry(self, model, prompt, refs, width, height, seed=None) -> ImageResult:
        try:
            return await self._provider.generate(model, prompt, refs, width, height, seed)
        except (RunwareGenerationError, asyncio.TimeoutError) as e:
            logger.warning("runware first attempt failed: {}", e)
            return await self._provider.generate(model, prompt, refs, width, height, seed)

    async def _finish(self, gen_id, user_id, status, image, cost, error, url=None, seed=None) -> GenerationOutcome:
        async with self._sf() as s:
            gen = await s.get(Generation, gen_id)
            gen.status, gen.cost_usd, gen.error, gen.finished_at = status, cost, error, utcnow()
            if status == "done":
                # Ссылка Runware живёт ~7 дней: её хватает для «Скачать в HD».
                gen.result_url = url
                # Сид нужен «Своей детали»: правка держится того же кадра.
                gen.seed = seed
            else:
                await wallet.refund_generation(s, user_id, gen_id)
            await s.commit()
        return GenerationOutcome(status, gen_id, image, cost, error, seed if status == "done" else None)


async def fail_stale_generations(session_factory, older_than_min: int = 5) -> int:
    cutoff = utcnow() - timedelta(minutes=older_than_min)
    n = 0
    async with session_factory() as s:
        rows = await s.execute(
            select(Generation).where(Generation.status == "running", Generation.started_at < cutoff)
        )
        for gen in rows.scalars().all():
            gen.status, gen.error, gen.finished_at = "failed", "stale on startup", utcnow()
            await wallet.refund_generation(s, gen.user_id, gen.id)
            n += 1
        await s.commit()
    return n
