"""В канале только три оценки и платная реакция звёздами."""
import httpx
from loguru import logger

# 👍 хорошо, 👎 не очень, 🔥 высший балл. paid — звёзды, по желанию.
CHANNEL_REACTIONS = (
    {"type": "emoji", "emoji": "👍"},
    {"type": "emoji", "emoji": "👎"},
    {"type": "emoji", "emoji": "🔥"},
    {"type": "paid"},
)


def reactions_body(chat_id: int | str) -> dict:
    return {"chat_id": chat_id, "available_reactions": list(CHANNEL_REACTIONS)}


async def allow_channel_reactions(token: str, chat_id: int | str) -> bool:
    """Оставляет в канале 👍, 👎, 🔥 и платные реакции. Остальные прячет."""
    url = f"https://api.telegram.org/bot{token}/setChatAvailableReactions"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, json=reactions_body(chat_id))
        data = response.json()
    except Exception as e:
        logger.warning("channel reactions request failed: {}", e)
        return False
    if not data.get("ok"):
        logger.warning("channel reactions not set: {}", data.get("description"))
        return False
    logger.info("channel reactions set for {}", chat_id)
    return True
