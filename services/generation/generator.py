import logging
from typing import Any, Dict, Optional
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Generation

logger = logging.getLogger(__name__)


async def prepare_runware_payload(
    prompt: str,
    reference_image_url: Optional[str] = None,
    seed: Optional[int] = None,
    is_edit_mode: bool = False,
) -> Dict[str, Any]:
    """Формирует payload для Runware API с фиксацией единого разрешения и параметров."""
    payload = {
        "positivePrompt": prompt,
        "width": 1024,
        "height": 1536,
        "steps": 30,
        "CFGScale": 7.0,
        "numberResults": 1,
        "outputFormat": "WEBP",
    }

    if seed is not None:
        payload["seed"] = seed

    if is_edit_mode and reference_image_url:
        payload["seedImage"] = reference_image_url
        payload["strength"] = 0.45  # Сохраняет 55% исходного кадра и меняет детали

    return payload


async def fail_stale_generations(session: AsyncSession) -> None:
    """Завершает зависшие сессии генерации со статусом processing при перезапуске."""
    try:
        stmt = (
            update(Generation)
            .where(Generation.status == "processing")
            .values(status="failed", error_message="Server restarted")
        )
        await session.execute(stmt)
        await session.commit()
        logger.info("Stale generations successfully updated to failed.")
    except Exception as e:
        logger.error(f"Failed to cleanup stale generations: {e}")


class TelegramFileFetcher:
    """Вспомогательный класс для скачивания и подготовки файлов из Telegram."""

    def __init__(self, bot: Any):
        self.bot = bot

    async def get_file_url(self, file_id: str) -> Optional[str]:
        try:
            file = await self.bot.get_file(file_id)
            return f"https://api.telegram.org/file/bot{self.bot.token}/{file.file_path}"
        except Exception as e:
            logger.error(f"Failed to fetch Telegram file URL for {file_id}: {e}")
            return None


class Generator:
    """Основной класс-сервис для обработки задач генерации изображений."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def generate(
        self,
        prompt: str,
        reference_image_url: Optional[str] = None,
        seed: Optional[int] = None,
        is_edit_mode: bool = False,
    ) -> Dict[str, Any]:
        return await prepare_runware_payload(
            prompt=prompt,
            reference_image_url=reference_image_url,
            seed=seed,
            is_edit_mode=is_edit_mode,
        )
