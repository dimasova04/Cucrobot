"""Каталог видео. Лайт открыт всем, жёсткие видны сразу и требуют подписку.

Ролик-образец для сцены кладётся в assets/video_refs/<id>.mp4.
Пока файла нет, сцена собирается по тексту. Когда файл появится, движение ориентируется на него.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Clip:
    id: str
    name: str
    prompt: str
    locked: bool


REFS_DIR = Path(__file__).resolve().parent.parent / "assets" / "video_refs"

# [solo] — в кадре только девушка с фото.
CLIPS: tuple[Clip, ...] = (
    Clip(
        "walk", "Идёт к камере",
        "[solo] indoors, full body. Она в облегающем платье идёт к камере, улыбается.",
        False,
    ),
    Clip(
        "dance", "Танцует",
        "[solo] indoors, full body. Она в мини-юбке и топе медленно танцует и смотрит в камеру.",
        False,
    ),
    Clip(
        "turn", "Поворот",
        "[solo] indoors, full body. Она в обтягивающих шортах и топе поворачивается к камере и улыбается.",
        False,
    ),
    Clip(
        "sit", "Садится",
        "[solo] indoors, a chair, full body. Она в бикини садится и смотрит в камеру.",
        False,
    ),
    Clip(
        "wave", "Машет рукой",
        "[solo] outdoors in daylight, full body. Она в вечернем платье машет рукой и улыбается.",
        False,
    ),
    Clip(
        "hair", "Поправляет волосы",
        "[solo] indoors, full body. Она в рубашке и юбке поправляет волосы и смотрит в камеру.",
        False,
    ),
    Clip(
        "undress", "Снимает всё",
        "[solo] indoors, full body. Взрослая женщина одна снимает с себя одежду и остаётся без одежды, смотрит в камеру.",
        True,
    ),
    Clip(
        "bed", "На кровати",
        "[solo] on a bed in a bedroom, full body. Взрослая женщина одна, без одежды, двигается на кровати и смотрит в камеру.",
        True,
    ),
    Clip(
        "chair", "В кресле",
        "[solo] indoors, an armchair, full body. Взрослая женщина одна, без одежды, сидит в кресле с раздвинутыми ногами и смотрит в камеру.",
        True,
    ),
    Clip(
        "shower", "В душе",
        "[solo] in a shower, full body. Взрослая женщина одна, без одежды, стоит под водой и смотрит в камеру.",
        True,
    ),
    Clip(
        "knees", "На коленях",
        "[solo] on a bed, full body. Взрослая женщина одна, без одежды, стоит на коленях и смотрит в камеру.",
        True,
    ),
    Clip(
        "stomach", "Лежит на животе",
        "[solo] on a bed, full body. Взрослая женщина одна, без одежды, лежит на животе и смотрит в камеру.",
        True,
    ),
)

_BY_ID = {item.id: item for item in CLIPS}


def get_clip(clip_id: str | None) -> Clip | None:
    if not clip_id:
        return None
    return _BY_ID.get(clip_id)


def light_clips() -> list[Clip]:
    return [item for item in CLIPS if not item.locked]


def hard_clips() -> list[Clip]:
    return [item for item in CLIPS if item.locked]


def ref_file(clip: Clip) -> Path | None:
    """Файл-образец, если его уже положили. Имя файла — id сцены."""
    path = REFS_DIR / f"{clip.id}.mp4"
    return path if path.is_file() else None
