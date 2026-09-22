import asyncio
from dataclasses import dataclass
from typing import Protocol

from loguru import logger


class RunwareGenerationError(Exception):
    pass


@dataclass
class ImageResult:
    url: str
    cost: float | None
    nsfw: bool


class ImageProvider(Protocol):
    async def generate(self, model: str, prompt: str, refs: list[str], width: int, height: int) -> ImageResult: ...


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

    async def generate(self, model: str, prompt: str, refs: list[str], width: int, height: int) -> ImageResult:
        from runware import IImageInference

        client = await self._get()
        req = IImageInference(
            model=model,
            positivePrompt=prompt,
            width=width,
            height=height,
            numberResults=1,
            includeCost=True,
            outputType="URL",
            outputFormat="JPG",
            safety={"checkContent": True},
            inputs={"referenceImages": refs},
        )
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
        logger.info("runware ok model={} cost={} nsfw={}", model, img.cost, img.NSFWContent)
        return ImageResult(url=url, cost=img.cost, nsfw=bool(img.NSFWContent))

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            finally:
                self._client = None
