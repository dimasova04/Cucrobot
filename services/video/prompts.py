"""Короткие действия и свой текст. Свой текст уходит как есть, с одной фразой про этот кадр."""

VIDEO_PROMPT_MAX = 2000

# Кнопка сама описывает движение. Лица и место остаются с фото.
# У «трутся» и раздеваний одежда как раз должна меняться — там нет фразы same clothes.
ACTIONS = {
    "auto": (
        "The people already in this photo come alive for a few seconds. "
        "Natural blinking, breathing, a small shift of weight, hair and clothes moving slightly. "
        "Same faces, same clothes, same place, same framing. "
        "Do not add anyone. Do not change who is in the frame."
    ),
    "closer": (
        "Slowly move the camera closer to the people already in this photo. "
        "They notice it and look toward the lens. "
        "Same faces, same clothes, same place. Do not add anyone."
    ),
    "kiss": (
        "The people already in this photo lean toward each other and kiss. "
        "Keep their faces recognizable. Same clothes and place. Do not add anyone."
    ),
    "hug": (
        "The people already in this photo turn to each other and embrace. "
        "Same faces, same clothes, same place. Do not add anyone."
    ),
    "dance": (
        "The people already in this photo start a slow dance together. "
        "Same faces, same clothes, same place. Do not add anyone."
    ),
    "rub": (
        "The people already in this photo step close and slowly rub their bodies against each other. "
        "Keep their faces recognizable. Same place and framing. "
        "Do not add anyone. Do not change who is in the frame."
    ),
    "undress_him": (
        "One person already in this photo unbuttons the man's shirt and slides it off his shoulders, then drops it. "
        "Leave his other clothes on. Keep their faces recognizable. Same place and framing. "
        "Do not add anyone."
    ),
    "undress_top": (
        "The woman already in this photo takes off her outer layer, a jacket, coat or cardigan, and drops it. "
        "Leave the clothes underneath on. Keep her face recognizable. Same place and framing. "
        "Do not add anyone."
    ),
}


def video_prompt(action: str, custom: str | None = None) -> str:
    if action == "custom":
        text = (custom or "").strip()
        return f"Animate this exact photo. {text}"
    if action not in ACTIONS:
        raise KeyError(action)
    return ACTIONS[action]
