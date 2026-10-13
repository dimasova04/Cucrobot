"""Классические образы. Первый блок открыт всем, второй виден сразу и требует подписку."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Look:
    id: str
    name: str
    prompt: str
    locked: bool


# [solo] — в кадре только девушка с фото. Префикс в текст модели не попадает.
LOOKS: tuple[Look, ...] = (
    Look(
        "bikini", "В бикини",
        "[solo] outdoors in daylight, full body. Она в тёмном бикини, улыбается и смотрит в камеру.",
        False,
    ),
    Look(
        "skirt", "В мини-юбке",
        "[solo] indoors, full body. Она в короткой мини-юбке и топе, улыбается и смотрит в камеру.",
        False,
    ),
    Look(
        "shorts", "В обтягивающих шортах",
        "[solo] indoors, full body. Она в обтягивающих шортах и топе, улыбается и смотрит в камеру.",
        False,
    ),
    Look(
        "dress", "В облегающем платье",
        "[solo] indoors, full body. Она в облегающем коротком платье, улыбается и смотрит в камеру.",
        False,
    ),
    Look(
        "top", "В кроп-топе",
        "[solo] indoors, full body. Она в кроп-топе и коротких шортах, улыбается и смотрит в камеру.",
        False,
    ),
    Look(
        "jeans", "В джинсах",
        "[solo] indoors, full body. Она в узких джинсах и топе, улыбается и смотрит в камеру.",
        False,
    ),
    Look(
        "shirt", "В рубашке",
        "[solo] indoors, full body. Она в застёгнутой белой рубашке и короткой юбке, улыбается и смотрит в камеру.",
        False,
    ),
    Look(
        "evening", "В вечернем платье",
        "[solo] indoors, evening light, full body. Она в длинном вечернем платье, улыбается и смотрит в камеру.",
        False,
    ),
    Look(
        "nude", "Полностью без всего",
        "[solo] indoors, soft daylight, full body. Взрослая женщина одна в кадре, полностью без одежды, стоит и смотрит в камеру.",
        True,
    ),
    Look(
        "bed", "Ню на кровати",
        "[solo] on a bed in a bedroom, warm light, full body. Взрослая женщина одна, без одежды, лежит на кровати и смотрит в камеру.",
        True,
    ),
    Look(
        "chair", "В кресле с раздвинутыми ногами",
        "[solo] indoors, an armchair, full body. Взрослая женщина одна, без одежды, сидит в кресле с раздвинутыми ногами и смотрит в камеру.",
        True,
    ),
    Look(
        "shower", "Ню в душе",
        "[solo] in a shower with tile and glass, full body. Взрослая женщина одна, без одежды, стоит под водой и смотрит в камеру.",
        True,
    ),
    Look(
        "mirror", "Ню у зеркала",
        "[solo] in front of a bedroom mirror, full body. Взрослая женщина одна, без одежды, смотрит в зеркало.",
        True,
    ),
    Look(
        "stomach", "Лежит на животе",
        "[solo] on a bed, full body. Взрослая женщина одна, без одежды, лежит на животе и смотрит в камеру.",
        True,
    ),
    Look(
        "knees", "На коленях на кровати",
        "[solo] on a bed, full body. Взрослая женщина одна, без одежды, стоит на коленях на кровати и смотрит в камеру.",
        True,
    ),
    Look(
        "floor", "Ню на полу",
        "[solo] on the floor of a bedroom, full body. Взрослая женщина одна, без одежды, сидит на полу и смотрит в камеру.",
        True,
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
