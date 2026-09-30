from aiogram.fsm.state import State, StatesGroup

from bot import texts
from services.billing import subscriptions
from services.generation.content_filter import is_allowed
from services.generation.generator import GenerationRequest


class GenStates(StatesGroup):
    person1 = State()
    actor1 = State()
    hero = State()
    scene = State()
    custom_scene = State()
    detail = State()
    result = State()


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
    return {
        "people": [], "actors": [], "hero_file_id": None,
        "scene_id": None, "custom_text": None, "custom_file_id": None, "detail": None,
    }


def effective_tier(user) -> str:
    """Качество пользователя из профиля, с даунгрейдом до base без активной подписки."""
    tier = getattr(user, "preferred_tier", None) or "base"
    if tier == "premium" and not subscriptions.is_active(user):
        return "base"
    return tier


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


def result_buttons(data: dict) -> list[tuple[str, str]]:
    """Кнопки под результатом. Последняя кнопка («Новое фото») всегда идёт
    отдельной строкой во всю ширину — см. keyboards.result_kb."""
    buttons = [
        (texts.BTN_MORE, "gen:more"),
        (texts.BTN_CHANGE_SCENE, "gen:change_scene"),
        (texts.BTN_CHANGE_ACTOR, "gen:change_actor"),
    ]
    # «Ещё актёр» не показываем со «своим героем»: его нельзя смешивать с каталогом.
    if not data.get("hero_file_id") and len(data.get("actors") or []) == 1:
        buttons.append((texts.BTN_ADD_ACTOR, "gen:add_actor"))
    buttons.append((texts.BTN_DETAIL, "gen:detail"))
    gen_id = data.get("last_generation_id")
    if gen_id:
        buttons.append((texts.BTN_HD, f"gen:hd:{gen_id}"))
    buttons.append((texts.BTN_NEW_PHOTO, "gen:new"))
    return buttons


def is_complete(data: dict) -> bool:
    return bool(
        data.get("people")
        and (data.get("actors") or data.get("hero_file_id"))
        and (data.get("scene_id") or data.get("custom_text") or data.get("custom_file_id"))
    )


def request_from_state(user_id: int, data: dict, tier: str) -> GenerationRequest:
    return GenerationRequest(
        user_id=user_id,
        people_file_ids=list(data["people"]),
        actor_ids=list(data["actors"]),
        hero_file_id=data.get("hero_file_id"),
        scene_id=data.get("scene_id"),
        custom_scene_text=data.get("custom_text"),
        custom_scene_file_id=data.get("custom_file_id"),
        detail=data.get("detail"),
        tier=tier,
    )
