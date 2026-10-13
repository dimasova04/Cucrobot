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
from services.generation import faces
from services.generation.local_assets import is_asset_ref, resolve_asset
from services.generation.prompt_builder import (
    NEGATIVE_PROMPT, ActorInput, GenerationInput, build, build_edit, build_insert,
    is_quality_request, sdxl_adapter_groups,
)
from services.generation.runware_client import ImageProvider, ImageResult, RunwareGenerationError


# CyberRealistic XL Play v10, основной fp16. Тот же вес, что в Dimasova/neonclub-checkpoints.
# Civitai отдаёт его Runware по этому AIR, отдельная заливка не нужна и денег за хранение нет.
CYBERREALISTIC_AIR = "civitai:312530@2840768"
SDXL_MAX_REFS = 4
# Родной портрет модели: 832×1216. Кадр 2K у SDXL считает дольше и рисует лишние конечности.
_SDXL_PORTRAIT = (832, 1216)
_SDXL_LANDSCAPE = (1216, 832)


class AlreadyRunning(Exception):
    pass


CAST_NOTES = {
    "watch": "Person B is in the frame only watching the others. He does not touch them.",
    "join": "Person B is in the frame together with the others and takes part in the same pose.",
}


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
    # Имена не из каталога: (имя для промпта, file_id фото, можно пусто).
    named_actors: list[tuple[str, list[str]]] | None = None
    # watch / join — только если на фото есть человек пользователя.
    self_role: str | None = None
    # Вписать человека в готовый кадр. Вместе с edit_mode и base_generation_id.
    insert_prompt: str | None = None
    # person — последнее фото пользователя; actor — последний id каталога;
    # named — последний названный. От этого зависит, чьё лицо уйдёт в модель.
    insert_target: str | None = None
    base_generation_id: int | None = None
    edit_mode: bool = False
    # False — кадр для ролика: кристаллики списывает оживление, не эта картинка.
    bill: bool = True


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
        if is_asset_ref(file_id):
            data = resolve_asset(file_id).read_bytes()
        else:
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
        # Обычное фото — свой SDXL. Квен и Клинг подменяли человека и стоят дороже.
        # Старый AIR на сервере это не перебивает.
        return CYBERREALISTIC_AIR, SDXL_MAX_REFS, s.cost_base

    def _sdxl_frame(self, width: int, height: int) -> tuple[int, int]:
        """Чужой кадр, в том числе 2K Клинга, на этот чекпоинт не отправляем."""
        if height >= width:
            return _SDXL_PORTRAIT
        return _SDXL_LANDSCAPE

    def _uses_sdxl(self, tier: str) -> bool:
        return tier != "premium"

    def _sdxl_call(self, inp: GenerationInput, max_refs: int, mode: str, previous: str | None, detail: str) -> dict:
        s = self._settings
        quality = mode == "edit" and is_quality_request(detail)
        groups = [] if quality else sdxl_adapter_groups(inp, max_refs, mode)
        adapters = []
        for role, images in groups:
            if not images:
                continue
            if role == "place":
                if s.sdxl_place_weight > 0:
                    adapters.append({
                        "model": s.sdxl_place_air,
                        "guideImages": images[:1],
                        "weight": s.sdxl_place_weight,
                        "weightType": "composition",
                    })
                continue
            # Целое фото, не кроп: обрезанный кадр Runware отклоняет, и генерация падает.
            adapters.append({
                "model": s.sdxl_face_air,
                "guideImages": [images[0]],
                "weight": s.sdxl_face_weight,
            })
        if mode == "insert":
            strength = s.sdxl_insert_strength
            seed_image = previous
        elif mode == "edit":
            strength = s.sdxl_quality_strength if quality else s.sdxl_edit_strength
            seed_image = previous
        else:
            # Новый кадр не стартует с фото: вместе с адаптером Runware такой запрос не принимает.
            seed_image = None
            strength = None
        return {
            "family": "sdxl",
            "negative": NEGATIVE_PROMPT,
            "steps": s.model_base_steps,
            "cfg": s.model_base_cfg,
            "scheduler": s.model_base_scheduler,
            "ip_adapters": adapters,
            "seed_image": seed_image,
            "strength": strength,
        }

    async def run(self, req: GenerationRequest) -> GenerationOutcome:
        if req.user_id in self._running:
            raise AlreadyRunning()
        self._running.add(req.user_id)
        try:
            return await self._run(req)
        finally:
            self._running.discard(req.user_id)

    async def _run(self, req: GenerationRequest) -> GenerationOutcome:
        named = list(req.named_actors or [])
        if not req.actor_ids and not named and not req.people_file_ids:
            raise ValueError("request needs at least one actor")
        model_air, max_refs, cost = self._model(req.tier)
        if not req.bill:
            cost = 0

        async with self._sf() as s:
            # Выключенный актёр — то же самое, что несуществующий: его могли
            # отключить, пока сессия пользователя висела в FSM.
            actors = [a for a in [await catalog.get_actor(s, i) for i in req.actor_ids] if a and a.is_active]
            if len(actors) != len(req.actor_ids):
                raise ValueError("unknown or inactive actor id")
            scene = await catalog.get_scene(s, req.scene_id) if req.scene_id else None
            if scene:
                scene_prompt, orientation, location = scene.prompt, scene.orientation, scene.name
                scene_ref_ids = catalog.scene_ref_ids(scene)
            elif req.custom_scene_file_id:
                scene_prompt, orientation, location = "in the setting shown", "portrait", "custom:photo"
                scene_ref_ids = [req.custom_scene_file_id]
            else:
                scene_prompt, orientation, location = (req.custom_scene_text or ""), "portrait", "custom:text"
                scene_ref_ids = []

            base = await self._edit_base(s, req)

            if cost:
                balance = await wallet.get_balance(s, req.user_id)
                if balance < cost:
                    raise wallet.InsufficientCrystals(needed=cost, balance=balance)
            actors_json = [{"id": a.id, "name": a.name} for a in actors]
            actors_json += [{"id": None, "name": name} for name, _files in named]
            gen = Generation(
                user_id=req.user_id, model_air=model_air, model_tier=req.tier,
                actors=actors_json,
                location=location, user_detail=req.detail or req.insert_prompt, crystals_charged=cost,
            )
            s.add(gen)
            await s.flush()
            if cost:
                await wallet.charge_generation(s, req.user_id, cost, gen.id)
            await s.commit()
            gen_id = gen.id
            actor_inputs = [
                ActorInput(a.name, a.description, catalog.usable_ref_ids([r.file_id for r in a.refs]))
                for a in actors
            ]
            actor_inputs += [ActorInput(name, "", list(files)) for name, files in named]

        try:
            people = [_data_uri(await self._fetcher.fetch(f)) for f in req.people_file_ids]
            for ai in actor_inputs:
                ai.refs = [_data_uri(await self._fetcher.fetch(f)) for f in ai.refs]
            # Лица с кадра локации не отдаём модели: иначе она оставляет того мужчину
            # вместо выбранного актёра. Ракурс и место на фото остаются.
            scene_refs = [
                _data_uri(faces.anonymize_faces(await self._fetcher.fetch(fid)))
                for fid in scene_ref_ids
            ]
            width, height = self._settings.frame_size(req.tier, orientation)
            if req.tier != "premium":
                width, height = self._sdxl_frame(width, height)
            # Каталожные идут первыми, названные — следом. Новый каталожный поэтому
            # не последний в общем списке, если в кадре уже есть названный.
            insert_index = None
            if req.insert_prompt and req.insert_target == "actor":
                insert_index = len(req.actor_ids) - 1
            elif req.insert_prompt and req.insert_target == "named":
                insert_index = len(actor_inputs) - 1
            inp = GenerationInput(
                people, actor_inputs, scene_prompt, scene_refs[0] if scene_refs else None, req.detail, width, height,
                cast_note=CAST_NOTES.get(req.self_role or ""),
                scene_refs=scene_refs,
                insert_target=req.insert_target if req.insert_prompt else None,
                insert_actor_index=insert_index,
            )
            previous_image, seed = await self._load_base_image(base)
            sdxl = self._uses_sdxl(req.tier)
            if req.tier == "premium":
                style = "instruct"
            else:
                style = "sdxl"
            if previous_image and req.insert_prompt:
                mode = "insert"
                prompt, refs = build_insert(
                    inp, previous_image, req.insert_prompt, max_refs=max_refs, style=style,
                )
            elif previous_image:
                mode = "edit"
                prompt, refs = build_edit(
                    inp, previous_image, req.detail or "", max_refs=max_refs, style=style,
                )
            else:
                mode = "fresh"
                seed = None  # обычная генерация: каждый кадр со своим сидом
                prompt, refs = build(inp, max_refs=max_refs, style=style)
            extra = self._sdxl_call(inp, max_refs, mode, previous_image, req.detail or "") if sdxl else {}
            result = await self._generate_with_retry(model_air, prompt, refs, width, height, seed, extra)
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
        if not (req.edit_mode and req.base_generation_id and (req.detail or req.insert_prompt)):
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

    async def _generate_with_retry(self, model, prompt, refs, width, height, seed=None, extra=None) -> ImageResult:
        options = extra or {}
        try:
            return await self._provider.generate(model, prompt, refs, width, height, seed, **options)
        except (RunwareGenerationError, asyncio.TimeoutError) as e:
            logger.warning("runware first attempt failed: {}", e)
            return await self._provider.generate(model, prompt, refs, width, height, seed, **options)

    async def _finish(self, gen_id, user_id, status, image, cost, error, url=None, seed=None) -> GenerationOutcome:
        async with self._sf() as s:
            gen = await s.get(Generation, gen_id)
            gen.status, gen.cost_usd, gen.error, gen.finished_at = status, cost, error, utcnow()
            if status == "done":
                # Ссылка Runware живёт ~7 дней: её хватает для «Скачать в HD».
                gen.result_url = url
                # Сид нужен «Своей детали»: правка держится того же кадра.
                gen.seed = seed
            elif gen.crystals_charged:
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
