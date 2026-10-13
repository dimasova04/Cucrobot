"""Образы для фото. Любой образ списывает кристаллики."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Look:
    id: str
    name: str
    prompt: str
    locked: bool


# На одной странице семь рядов по две кнопки, как в примере каталога.
LOOKS_PER_PAGE = 14

# [solo] — в кадре только девушка с фото. Префикс в текст модели не попадает.
LOOKS: tuple[Look, ...] = (
    Look(
        "strip", "Снять всё 😭",
        "[solo] indoors, soft daylight, full body, one adult woman standing, completely nude, looking at the camera",
        True,
    ),
    Look(
        "lingerie", "⚡ В сексуальном белье 👙",
        "[solo] indoors, soft light, full body, one adult woman standing in a lace lingerie set, looking at the camera",
        False,
    ),
    Look(
        "stockings", "⚡ Голая в чулках 🖤",
        "[solo] indoors, soft light, full body, one adult woman standing, nude, wearing black stockings, looking at the camera",
        True,
    ),
    Look(
        "latex", "Переодеть в латекс 💄",
        "[solo] indoors, full body, one adult woman standing in a closed black latex catsuit, looking at the camera",
        False,
    ),
    Look(
        "bikini", "Примерить бикини 👙",
        "[solo] outdoors, daylight, full body, one adult woman in a dark bikini, smiling, looking at the camera",
        False,
    ),
    Look(
        "secretary", "Секретарша 👩‍💼",
        "[solo] in an office, full body, one adult woman in a white blouse, dark pencil skirt and heels, looking at the camera",
        False,
    ),
    Look(
        "wet", "⚡ Вся в 💧",
        "[solo] outdoors in the rain, full body, one adult woman in a wet white shirt and skirt, standing, looking at the camera",
        False,
    ),
    Look(
        "teacher", "Училка 👩‍🏫",
        "[solo] indoors in her office, full body, one adult woman in a white blouse, dark skirt and glasses, looking at the camera",
        False,
    ),
    Look(
        "pregnant", "Беременная 🤰",
        "[solo] indoors, full body, one adult pregnant woman in a fitted dress, standing, looking at the camera",
        False,
    ),
    Look(
        "bdsm", "БДСМ 👮‍♀️",
        "[solo] indoors, full body, one adult woman standing in a black leather harness and metal cuffs, looking at the camera",
        True,
    ),
    Look(
        "micro", "Мини-бикини 🔥",
        "[solo] on a beach, daylight, full body, one adult woman in a tiny dark bikini, smiling, looking at the camera",
        False,
    ),
    Look(
        "towel", "⚡ В полотенце",
        "[solo] in a bathroom, full body, one adult woman wrapped in a white bath towel, standing, looking at the camera",
        False,
    ),
    Look(
        "bunny", "Зайка 🐰",
        "[solo] indoors, full body, one adult woman in a closed black bunny costume with ears and a bow tie, looking at the camera",
        False,
    ),
)

_BY_ID = {item.id: item for item in LOOKS}


def get_look(look_id: str | None) -> Look | None:
    if not look_id:
        return None
    return _BY_ID.get(look_id)


def free_looks() -> list[Look]:
    return [item for item in LOOKS if not item.locked]


def locked_looks() -> list[Look]:
    return [item for item in LOOKS if item.locked]
