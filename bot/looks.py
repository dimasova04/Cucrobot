"""Образы для фото. Откровенные видны сразу и без подписки открывают оплату."""
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
        "[solo] indoors, soft daylight, full body. Взрослая женщина одна, полностью без одежды, стоит и смотрит в камеру.",
        True,
    ),
    Look(
        "lingerie", "⚡ В сексуальном белье 👙",
        "[solo] indoors, soft light, full body. Взрослая женщина в кружевном комплекте белья, стоит и смотрит в камеру.",
        False,
    ),
    Look(
        "stockings", "⚡ Голая в чулках 🖤",
        "[solo] indoors, soft light, full body. Взрослая женщина одна, без одежды, в чёрных чулках, стоит и смотрит в камеру.",
        True,
    ),
    Look(
        "latex", "Переодеть в латекс 💄",
        "[solo] indoors, full body. Взрослая женщина в закрытом чёрном латексном комбинезоне, стоит и смотрит в камеру.",
        False,
    ),
    Look(
        "bikini", "Примерить бикини 👙",
        "[solo] outdoors in daylight, full body. Она в тёмном бикини, улыбается и смотрит в камеру.",
        False,
    ),
    Look(
        "secretary", "Секретарша 👩‍💼",
        "[solo] in an office, full body. Взрослая женщина в белой блузке, тёмной юбке-карандаш и на каблуках, смотрит в камеру.",
        False,
    ),
    Look(
        "wet", "⚡ Вся в 💧",
        "[solo] outdoors in the rain, full body. Взрослая женщина в мокрой белой рубашке и юбке, стоит и смотрит в камеру.",
        False,
    ),
    Look(
        "teacher", "Училка 👩‍🏫",
        "[solo] indoors in her office, full body. Взрослая женщина в белой блузке, тёмной юбке и очках, стоит и смотрит в камеру.",
        False,
    ),
    Look(
        "pregnant", "Беременная 🤰",
        "[solo] indoors, full body. Взрослая беременная женщина в облегающем платье, стоит и смотрит в камеру.",
        False,
    ),
    Look(
        "bdsm", "БДСМ 👮‍♀️",
        "[solo] indoors, full body. Взрослая женщина одна, в чёрной кожаной портупее и наручниках, стоит и смотрит в камеру.",
        True,
    ),
    Look(
        "micro", "Мини-бикини 🔥",
        "[solo] on a beach, daylight, full body. Она в очень маленьком тёмном бикини, улыбается и смотрит в камеру.",
        False,
    ),
    Look(
        "towel", "⚡ В полотенце",
        "[solo] in a bathroom, full body. Взрослая женщина завернута в белое банное полотенце, стоит и смотрит в камеру.",
        False,
    ),
    Look(
        "bunny", "Зайка 🐰",
        "[solo] indoors, full body. Взрослая женщина в закрытом чёрном костюме зайки, с ушками и бабочкой, стоит и смотрит в камеру.",
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
