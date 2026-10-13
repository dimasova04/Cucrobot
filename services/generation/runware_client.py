import asyncio
import base64
from dataclasses import dataclass
from typing import Protocol

from loguru import logger

from services.generation.faces import jpeg_for_model


class RunwareGenerationError(Exception):
    pass


@dataclass
class ImageResult:
    url: str
    cost: float | None
    nsfw: bool
    # Сид кадра: нужен, чтобы правка детали держалась того же изображения.
    seed: int | None = None


def jpeg_data_uri(value: str | None, max_side: int = 1024) -> str | None:
    """Картинка для SDXL: настоящий JPEG. Не картинку не трогаем."""
    if not value or not value.startswith("data:") or "," not in value:
        return value
    try:
        raw = base64.b64decode(value.split(",", 1)[1])
    except Exception:
        return value
    shrunk = jpeg_for_model(raw, max_side=max_side)
    if not shrunk:
        return value
    return "data:image/jpeg;base64," + base64.b64encode(shrunk).decode()


def clean_scheduler(value: str | None) -> str | None:
    """Кавычки из переменной окружения Runware не принимает, и падает весь запрос."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().strip('"').strip("'").strip()
    return cleaned or None


# FLUX.2 klein — дистиллят на 4 шага. acceleration=high по умолчанию смазывает лицо,
# а CFG 3.5 тянет текст сильнее фото и дорисовывает татуировки.
KLEIN_AIR = "runware:400@2"
# Klein Anatomy Fixer 9B v1.5: только суставы и конечности. Вес 2 держит тот же кадр.
KLEIN_ANATOMY_LORA = "civitai:2324991@2615554"
KLEIN_ANATOMY_WEIGHT = 2.0
KLEIN_NEGATIVE = (
    "new tattoo, extra tattoo, tattoo on clear skin, different face, different body, "
    "changed figure, extra arm, third arm, extra hand, extra finger, six fingers, "
    "missing finger, fused fingers, melted hand, disconnected limb, floating hand, "
    "broken elbow, broken wrist, broken knee, merged bodies, duplicate torso, plastic skin"
)


def klein_identity_fields(fields: dict) -> dict:
    """Обычное фото: без ускорения и с низким CFG, чтобы кадр держал лицо и фигуру."""
    if fields.get("model") != KLEIN_AIR:
        return fields
    tuned = dict(fields)
    tuned["steps"] = 4
    tuned["CFGScale"] = 2
    tuned["acceleration"] = "none"
    tuned["negativePrompt"] = KLEIN_NEGATIVE
    tuned["lora"] = [{"model": KLEIN_ANATOMY_LORA, "weight": KLEIN_ANATOMY_WEIGHT}]
    return tuned


def kling_reference_fields(fields: dict) -> dict:
    """Kling IMAGE O1 с референсом берёт resolution, а не width и height.

    Вместе эти поля API отклоняет, кадра нет и кристалл возвращается.
    Промпт длиннее 2500 символов тоже отклоняется.
    """
    model = str(fields.get("model") or "")
    if not model.startswith("klingai:kling-image"):
        return fields
    out = {key: value for key, value in fields.items() if key not in ("width", "height")}
    out["resolution"] = "2k"
    prompt = out.get("positivePrompt") or ""
    if len(prompt) > 2500:
        cut = prompt[:2500].rsplit(" ", 1)[0]
        out["positivePrompt"] = cut or prompt[:2500]
    return out


def sdxl_retry_fields(fields: dict) -> dict | None:
    """Повтор без полей, из-за которых API отклоняет кадр целиком.

    Планировщик с кавычками, негативный промпт, стартовое фото и embedScaling
    роняют и новый кадр, и правку. Лица в адаптере остаются.
    """
    plain = {
        key: value
        for key, value in fields.items()
        if key not in ("strength", "scheduler", "negativePrompt")
    }
    inputs = {
        key: value
        for key, value in dict(plain.get("inputs") or {}).items()
        if key != "seedImage"
    }
    if inputs:
        plain["inputs"] = inputs
    else:
        plain.pop("inputs", None)
    adapters = []
    for item in plain.get("ipAdapters") or []:
        cleaned = {key: value for key, value in item.items() if key != "embedScaling"}
        if cleaned.get("guideImages"):
            adapters.append(cleaned)
    if adapters:
        plain["ipAdapters"] = adapters
    else:
        plain.pop("ipAdapters", None)
    if plain == fields:
        return None
    return plain


class ImageProvider(Protocol):
    async def generate(
        self, model: str, prompt: str, refs: list[str], width: int, height: int, seed: int | None = None,
        **options,
    ) -> ImageResult: ...


class RunwareClient:
    def __init__(self, api_key: str, timeout_sec: int = 90):
        self._api_key = api_key
        self._timeout = timeout_sec
        self._client = None
        self._lock = asyncio.Lock()

    async def _get(self):
        async with self._lock:
            if self._client is None:
                try:
                    from runware import Runware
                    client = Runware(api_key=self._api_key)
                    await asyncio.wait_for(client.connect(), timeout=15)
                except Exception as e:
                    self._client = None
                    raise RunwareGenerationError(f"connect failed: {e}") from e
                self._client = client
            return self._client

    async def generate(
        self, model: str, prompt: str, refs: list[str], width: int, height: int, seed: int | None = None,
        *, family: str = "reference", negative: str | None = None, steps: int | None = None,
        cfg: float | None = None, scheduler: str | None = None, ip_adapters: list | None = None,
        seed_image: str | None = None, strength: float | None = None,
    ) -> ImageResult:
        client = await self._get()
        fields = dict(
            model=model,
            seed=seed,
            positivePrompt=prompt,
            width=width,
            height=height,
            numberResults=1,
            includeCost=True,
            outputType="URL",
            outputFormat="JPG",
            outputQuality=95,
            safety={"checkContent": False},
        )
        if family == "sdxl":
            # SDXL не понимает referenceImages. Лица — IP-Adapter.
            # Правка кладёт прошлый кадр в inputs.seedImage: поле на верхнем уровне API отвергает.
            # Фото сжимаем: большой data URI или чужой формат роняют весь запрос.
            fields["negativePrompt"] = negative
            fields["steps"] = steps
            fields["CFGScale"] = cfg
            scheduler = clean_scheduler(scheduler)
            if scheduler:
                fields["scheduler"] = scheduler
            prepared = []
            for item in ip_adapters or []:
                guide = [jpeg_data_uri(image) for image in (item.get("guideImages") or [])]
                guide = [image for image in guide if image]
                if not guide:
                    continue
                prepared.append({**item, "guideImages": guide})
            if prepared:
                fields["ipAdapters"] = prepared
            seed_image = jpeg_data_uri(seed_image)
            if seed_image and strength is not None:
                fields["inputs"] = {"seedImage": seed_image}
                fields["strength"] = strength
        else:
            fields["inputs"] = {"referenceImages": refs}
            fields = klein_identity_fields(fields)
            fields = kling_reference_fields(fields)
        try:
            return await self._infer(client, fields)
        except RunwareGenerationError as first:
            if fields.get("acceleration") == "none":
                retry = {key: value for key, value in fields.items() if key != "acceleration"}
                logger.warning("klein request failed ({}), retrying with default acceleration", first)
                try:
                    return await self._infer(client, retry)
                except RunwareGenerationError as second:
                    first = second
                    fields = retry
            if fields.get("lora"):
                bare = {key: value for key, value in fields.items() if key != "lora"}
                logger.warning("klein anatomy lora failed ({}), retrying without it", first)
                return await self._infer(client, bare)
            if family != "sdxl":
                raise
            plain = sdxl_retry_fields(fields)
            if plain is None:
                raise
            logger.warning("sdxl request failed ({}), retrying without scheduler and seed image", first)
            return await self._infer(client, plain)

    async def _infer(self, client, fields: dict) -> ImageResult:
        from runware import IImageInference, ILora

        loras = fields.get("lora")
        if loras:
            fields = dict(fields)
            fields["lora"] = [
                item if not isinstance(item, dict) else ILora(model=item["model"], weight=item["weight"])
                for item in loras
            ]
        req = IImageInference(**fields)
        timeout = self._timeout
        model = str(fields.get("model") or "")
        civitai_lora = any(
            str(item.get("model", "")).startswith("civitai:")
            for item in loras or []
            if isinstance(item, dict)
        )
        if civitai_lora:
            # Первый запрос скачивает LoRA с Civitai. Короткий таймаут обрывает кадр.
            timeout = max(timeout, 180)
        if model.startswith("klingai:"):
            # Официальные примеры O1 — около 30–50 секунд. Короткий таймаут с сервера обрывает кадр.
            timeout = max(timeout, 120)
        elif model.startswith("civitai:"):
            # Первый запрос ещё скачивает чекпоинт. Повторный кадр уже из кэша Runware.
            timeout = max(timeout, 180)
        try:
            images = await asyncio.wait_for(client.imageInference(requestImage=req), timeout=timeout)
        except asyncio.TimeoutError:
            raise RunwareGenerationError(f"timeout after {timeout}s")
        except Exception as e:  # SDK raises RunwareAPIError / generic
            self._client = None  # force reconnect next time
            raise RunwareGenerationError(str(e)) from e
        if not images:
            raise RunwareGenerationError("empty result")
        img = images[0]
        url = getattr(img, "imageURL", None)
        if not url:
            raise RunwareGenerationError("no imageURL in result")
        result_seed = getattr(img, "seed", None)
        logger.info(
            "runware ok model={} cost={} nsfw={} seed={}",
            fields.get("model"), img.cost, img.NSFWContent, result_seed,
        )
        return ImageResult(
            url=url, cost=img.cost, nsfw=bool(img.NSFWContent),
            seed=int(result_seed) if result_seed is not None else None,
        )

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            finally:
                self._client = None
