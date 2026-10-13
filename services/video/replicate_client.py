"""Оживление кадра через Replicate. Токен только из env, в логи не пишется."""
import asyncio

import cv2
import httpx
import numpy as np
from loguru import logger

from services.video.prompts import video_prompt


class VideoError(Exception):
    pass


# 720p у Seedance часто рисуется три–четыре минуты. Короткий таймаут из env
# обрывает уже идущий ролик, и бот возвращает кристалл.
MIN_VIDEO_TIMEOUT_SEC = 420
# Длинная сторона больше этого чаще ловит ложный отказ «sensitive» и не влезает в гифку.
FRAME_MAX_SIDE = 1280


def seedance_input(image_url: str, prompt: str, seconds: int, resolution: str) -> dict:
    return {
        "image": image_url,
        "prompt": prompt,
        "duration": seconds,
        "resolution": resolution,
        "fps": 24,
        "camera_fixed": False,
    }


def wait_seconds(timeout_sec: int | None) -> int:
    return max(int(timeout_sec or 0), MIN_VIDEO_TIMEOUT_SEC)


def jpeg_frame(image: bytes, max_side: int = FRAME_MAX_SIDE) -> bytes:
    """Чётный JPEG не больше max_side. Не картинку отдаём как есть."""
    img = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return image
    height, width = img.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    if scale < 1:
        width = max(2, int(width * scale))
        height = max(2, int(height * scale))
        img = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
        height, width = img.shape[:2]
    width -= width % 2
    height -= height % 2
    if width < 2 or height < 2:
        return image
    img = img[:height, :width]
    ok, encoded = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        return image
    return encoded.tobytes()


def _snip(value) -> str:
    text = value if isinstance(value, str) else str(value or "")
    return " ".join(text.split())[:300]


class ReplicateVideo:
    def __init__(self, token: str, model: str, timeout_sec: int = MIN_VIDEO_TIMEOUT_SEC):
        self._token = token
        self._model = model
        self._timeout = wait_seconds(timeout_sec)

    async def animate(self, image: bytes, prompt: str, *, seconds: int, resolution: str) -> bytes:
        headers = {"Authorization": f"Bearer {self._token}"}
        timeout = httpx.Timeout(60.0, read=120.0)
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            image_url = await self._upload(client, jpeg_frame(image))
            prediction = await self._start(client, image_url, prompt, seconds, resolution)
            output_url = await self._wait(client, prediction)
            return await self._download(client, output_url)

    async def _upload(self, client: httpx.AsyncClient, image: bytes) -> str:
        response = await client.post(
            "https://api.replicate.com/v1/files",
            files={"content": ("frame.jpg", image, "image/jpeg")},
        )
        if response.status_code >= 400:
            logger.warning("replicate file upload failed: {} {}", response.status_code, _snip(response.text))
            raise VideoError(f"upload failed: {response.status_code}")
        url = (response.json().get("urls") or {}).get("get")
        if not url:
            raise VideoError("upload failed")
        return url

    async def _start(self, client: httpx.AsyncClient, image_url: str, prompt: str, seconds: int, resolution: str) -> dict:
        response = await client.post(
            f"https://api.replicate.com/v1/models/{self._model}/predictions",
            json={"input": seedance_input(image_url, prompt, seconds, resolution)},
        )
        if response.status_code >= 400:
            logger.warning("replicate prediction failed: {} {}", response.status_code, _snip(response.text))
            raise VideoError(f"prediction failed: {response.status_code} {_snip(response.text)}")
        data = response.json()
        if not data.get("id"):
            raise VideoError("prediction failed")
        logger.info("replicate video started id={} model={}", data["id"], self._model)
        return data

    async def _wait(self, client: httpx.AsyncClient, prediction: dict) -> str:
        url = (prediction.get("urls") or {}).get("get") or (
            f"https://api.replicate.com/v1/predictions/{prediction['id']}"
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout
        data = prediction
        while data.get("status") not in ("succeeded", "failed", "canceled"):
            if loop.time() > deadline:
                raise VideoError("timeout")
            await asyncio.sleep(2)
            response = await client.get(url)
            if response.status_code >= 400:
                raise VideoError("poll failed")
            data = response.json()
        if data.get("status") != "succeeded":
            reason = _snip(data.get("error") or data.get("status") or "failed")
            logger.warning("replicate video {} status={} error={}", prediction.get("id"), data.get("status"), reason)
            raise VideoError(reason)
        output = data.get("output")
        if isinstance(output, list):
            output = output[0] if output else None
        if not isinstance(output, str) or not output:
            raise VideoError("empty output")
        return output

    async def _download(self, client: httpx.AsyncClient, url: str) -> bytes:
        response = await client.get(url)
        if response.status_code >= 400 or not response.content:
            raise VideoError("download failed")
        return response.content


def prompt_for(action: str, custom: str | None = None) -> str:
    return video_prompt(action, custom)
