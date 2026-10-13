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
        try:
            return await self._infer(client, fields)
        except RunwareGenerationError as first:
            if family != "sdxl":
                raise
            plain = sdxl_retry_fields(fields)
            if plain is None:
                raise
            logger.warning("sdxl request failed ({}), retrying without scheduler and seed image", first)
            return await self._infer(client, plain)

    async def _infer(self, client, fields: dict) -> ImageResult:
        from runware import IImageInference

        req = IImageInference(**fields)
        try:
            images = await asyncio.wait_for(client.imageInference(requestImage=req), timeout=self._timeout)
        except asyncio.TimeoutError:
            raise RunwareGenerationError(f"timeout after {self._timeout}s")
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
