"""Оживление кадра через Replicate. Токен только из env, в логи не пишется."""
import asyncio

import httpx
from loguru import logger

from services.video.prompts import video_prompt


class VideoError(Exception):
    pass


def seedance_input(image_url: str, prompt: str, seconds: int, resolution: str) -> dict:
    return {
        "image": image_url,
        "prompt": prompt,
        "duration": seconds,
        "resolution": resolution,
        "fps": 24,
        "camera_fixed": False,
    }


class ReplicateVideo:
    def __init__(self, token: str, model: str, timeout_sec: int = 180):
        self._token = token
        self._model = model
        self._timeout = timeout_sec

    async def animate(self, image: bytes, prompt: str, *, seconds: int, resolution: str) -> bytes:
        headers = {"Authorization": f"Bearer {self._token}"}
        timeout = httpx.Timeout(60.0, read=60.0)
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            image_url = await self._upload(client, image)
            prediction = await self._start(client, image_url, prompt, seconds, resolution)
            output_url = await self._wait(client, prediction)
            return await self._download(client, output_url)

    async def _upload(self, client: httpx.AsyncClient, image: bytes) -> str:
        response = await client.post(
            "https://api.replicate.com/v1/files",
            files={"content": ("frame.jpg", image, "image/jpeg")},
        )
        if response.status_code >= 400:
            logger.warning("replicate file upload failed: {}", response.status_code)
            raise VideoError("upload failed")
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
            logger.warning("replicate prediction failed: {}", response.status_code)
            raise VideoError("prediction failed")
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
            logger.warning("replicate video {} status={}", prediction.get("id"), data.get("status"))
            raise VideoError(data.get("status") or "failed")
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
