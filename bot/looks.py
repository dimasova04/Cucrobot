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
# Образ меняет одежду. Кадр, лицо, фигура и внешность остаются с исходного фото.
_KEEP = (
    "Keep the source photograph: same frame, same face, same figure, same appearance. "
    "Do not replace this person. Change only the clothes: "
)
# «Сменить одежду» Клейн читает как переодеть. Снятие — отдельная команда.
_UNDRESS = (
    "Keep the source photograph: same frame, same face, same figure, same pose, same place. "
    "Do not replace this person. "
    "Remove the clothes she is wearing in this photo. Do not dress her in a new outfit. "
    "Natural adult chest: two breasts on the ribcage, one nipple on each, matching her figure. "
    "Natural adult vulva in its place between the thighs, one set only. "
)
LOOKS: tuple[Look, ...] = (
    Look(
        "strip", "Снять всё 😭",
        "[solo] " + _UNDRESS + "She is completely naked: no top, no bra, no skirt, no shorts, no belt, no underwear. "
        "Bare chest, bare stomach, bare hips.",
        True,
    ),
    Look(
        "lingerie", "⚡ В сексуальном белье 👙",
        "[solo] " + _KEEP + "a lace lingerie set",
        False,
    ),
    Look(
        "stockings", "⚡ Голая в чулках 🖤",
        "[solo] " + _UNDRESS + "She is naked except for black stockings. "
        "No top, no bra, no skirt, no belt, no underwear. Bare chest and bare hips.",
        True,
    ),
    Look(
        "latex", "Переодеть в латекс 💄",
        "[solo] " + _KEEP + "a closed black latex catsuit",
        False,
    ),
    Look(
        "bikini", "Примерить бикини 👙",
        "[solo] " + _KEEP + "a dark bikini",
        False,
    ),
    Look(
        "secretary", "Секретарша 👩‍💼",
        "[solo] " + _KEEP + "a white blouse, a dark pencil skirt and heels",
        False,
    ),
    Look(
        "wet", "⚡ Вся в 💧",
        "[solo] " + _KEEP + "a wet white shirt and skirt",
        False,
    ),
    Look(
        "teacher", "Училка 👩‍🏫",
        "[solo] " + _KEEP + "a white blouse, a dark skirt and glasses",
        False,
    ),
    Look(
        "pregnant", "Беременная 🤰",
        "[solo] Keep the source photograph: same frame, same face, same appearance. "
        "Do not replace this person. Change only the figure by a pregnant belly, and the clothes to a fitted dress",
        False,
    ),
    Look(
        "bdsm", "БДСМ 👮‍♀️",
        "[solo] " + _KEEP + "a black leather harness and metal cuffs",
        True,
    ),
    Look(
        "micro", "Мини-бикини 🔥",
        "[solo] " + _KEEP + "a tiny dark bikini",
        False,
    ),
    Look(
        "towel", "⚡ В полотенце",
        "[solo] " + _KEEP + "a white bath towel",
        False,
    ),
    Look(
        "bunny", "Зайка 🐰",
        "[solo] " + _KEEP + "a closed black bunny costume with ears and a bow tie",
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
