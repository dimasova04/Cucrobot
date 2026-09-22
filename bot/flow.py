from aiogram.fsm.state import State, StatesGroup

from bot import texts
from services.generation.content_filter import is_allowed
from services.generation.generator import GenerationRequest


class GenStates(StatesGroup):
    person1 = State()
    person2 = State()
    actor1 = State()
    actor2 = State()
    scene = State()
    custom_scene = State()
    detail = State()
    model = State()
    confirm = State()


ACTORS_PER_PAGE = 10
SCENES_PER_PAGE = 12


def paginate(items: list, page: int, size: int) -> tuple[list, bool, bool]:
    """Возвращает (срез страницы, есть ли предыдущая, есть ли следующая).
    Номер страницы с нуля, выход за границы зажимается."""
    if size <= 0:
        raise ValueError("size must be positive")
    last_page = max(0, (len(items) - 1) // size)
    page = max(0, min(page, last_page))
    start = page * size
    return items[start : start + size], page > 0, start + size < len(items)


def empty_data() -> dict:
    return {"people": [], "actors": [], "scene_id": None, "custom_text": None, "custom_file_id": None, "detail": None, "tier": "base"}


def validate_detail(text: str) -> str | None:
    if len(text) > 100:
        return texts.DETAIL_TOO_LONG
    if not is_allowed(text):
        return texts.TEXT_REJECTED
    return None


def validate_custom_scene(text: str) -> str | None:
    if len(text) > 200:
        return texts.CUSTOM_SCENE_TOO_LONG
    if not is_allowed(text):
        return texts.TEXT_REJECTED
    return None


def scene_label(data: dict, scene_name: str | None) -> str:
    if data.get("scene_id") and scene_name:
        return scene_name
    if data.get("custom_file_id"):
        return texts.CUSTOM_SCENE_LABEL_PHOTO
    return texts.CUSTOM_SCENE_LABEL_TEXT


def summary(data: dict, actors_names: list[str], scene_name: str, model_tier: str, cost: int, balance: int) -> str:
    return texts.CONFIRM.format(
        people=len(data.get("people", [])),
        actors=", ".join(actors_names),
        scene=scene_name,
        detail=data.get("detail") or texts.DETAIL_NONE,
        model=texts.MODEL_NAMES[model_tier],
        cost=cost,
        balance=balance,
    )


def is_complete(data: dict) -> bool:
    return bool(
        data.get("people")
        and data.get("actors")
        and (data.get("scene_id") or data.get("custom_text") or data.get("custom_file_id"))
    )


def request_from_state(user_id: int, data: dict, tier: str) -> GenerationRequest:
    return GenerationRequest(
        user_id=user_id,
        people_file_ids=list(data["people"]),
        actor_ids=list(data["actors"]),
        scene_id=data.get("scene_id"),
        custom_scene_text=data.get("custom_text"),
        custom_scene_file_id=data.get("custom_file_id"),
        detail=data.get("detail"),
        tier=tier,
    )
