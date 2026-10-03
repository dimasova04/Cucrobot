from aiogram.fsm.state import State, StatesGroup

from bot import texts
from services.billing import subscriptions
from services.generation.content_filter import is_allowed
from services.generation.generator import GenerationRequest


class GenStates(StatesGroup):
    person1 = State()
    actor1 = State()
    actor_name = State()
    actor_photos = State()
    scene = State()
    custom_scene = State()
    detail = State()
    self_role = State()
    self_photo = State()
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
        "people": [], "actors": [], "named": [],
        "self_file_id": None, "self_role": None,
        "scene_id": None, "custom_text": None, "custom_file_id": None, "detail": None,
        # Чистый кадр и все «свои детали» одним текстом: каждая новая деталь
        # правит его, а не предыдущую правку, иначе лица и руки плывут.
        "details": [], "plate_generation_id": None,
    }


def norm_name(name: str) -> str:
    return " ".join((name or "").strip().lower().replace("ё", "е").split())


INSERT_SELF = {
    "watch": (
        "Add person B into this exact photo. He stands nearby and only watches the people already there. "
        "He does not touch them. Keep the same place, clothes, pose and faces of everyone already in the photo. "
        "Do not redraw the scene."
    ),
    "join": (
        "Add person B into this exact photo so he takes part in the same pose with the people already there. "
        "Keep the same place and the faces of everyone already in the photo. Do not redraw the scene."
    ),
}


def insert_actor_prompt(name: str) -> str:
    return (
        f"Add {name} into this exact photo beside the people already there. "
        "Keep the same place, clothes and pose of everyone already in the photo. Do not redraw the scene."
    )


def effective_tier(user) -> str:
    """Качество пользователя из профиля, с даунгрейдом до base без активной подписки."""
    tier = getattr(user, "preferred_tier", None) or "base"
    if tier == "premium" and not subscriptions.is_active(user):
        return "base"
    return tier


def compose_details(details: list[str] | None) -> str | None:
    """Одна деталь остаётся как есть, несколько склеиваются в одну правку кадра."""
    parts = [part.strip() for part in (details or []) if part and part.strip()]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return ". ".join(part.rstrip(".") for part in parts)


DETAIL_MAX_LEN = 300


def validate_detail(text: str) -> str | None:
    if len(text) > DETAIL_MAX_LEN:
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
    """Кнопки под результатом. Последняя кнопка («Новая фотосессия») всегда идёт
    отдельной строкой во всю ширину — см. keyboards.result_kb."""
    buttons = [
        (texts.BTN_MORE, "gen:more"),
        (texts.BTN_CHANGE_SCENE, "gen:change_scene"),
        (texts.BTN_ADD_PERSON, "gen:add_person"),
        (texts.BTN_DETAIL, "gen:detail"),
    ]
    gen_id = data.get("last_generation_id")
    if gen_id:
        buttons.append((texts.BTN_HD, f"gen:hd:{gen_id}"))
    buttons.append((texts.BTN_NEW_PHOTO, "gen:new"))
    return buttons


def add_person_buttons(data: dict) -> list[tuple[str, str]]:
    """Себя можно вписать один раз. Другого актёра — сколько угодно разных."""
    buttons = []
    if not data.get("self_file_id"):
        buttons.append((texts.BTN_ADD_SELF, "add:self"))
    buttons.append((texts.BTN_ADD_OTHER, "add:other"))
    return buttons


def is_complete(data: dict) -> bool:
    pending = data.get("pending_insert") or {}
    has_actor = bool(data.get("actors") or data.get("named") or pending.get("kind") in ("actor", "named"))
    has_scene = bool(data.get("scene_id") or data.get("custom_text") or data.get("custom_file_id"))
    return bool(data.get("people") and has_actor and has_scene)


def name_taken(data: dict, name: str) -> bool:
    key = norm_name(name)
    if not key:
        return False
    return any(norm_name(item.get("name", "")) == key for item in data.get("named") or [])


def commit_pending(data: dict) -> None:
    """После удачной генерации человек остаётся в сессии для пересъёмки и новой сцены."""
    pending = data.pop("pending_insert", None)
    if not pending:
        return
    if pending["kind"] == "self":
        data["people"].append(pending["file_id"])
        data["self_file_id"] = pending["file_id"]
        data["self_role"] = pending["role"]
    elif pending["kind"] == "actor":
        if pending["actor_id"] not in data["actors"]:
            data["actors"].append(pending["actor_id"])
    else:
        data.setdefault("named", []).append({"name": pending["name"], "files": list(pending["files"])})


def apply_catalog_scene(data: dict, scene_id: int) -> dict:
    """Новая сцена из каталога — свежий кадр: прошлая деталь не переносится."""
    data["scene_id"] = scene_id
    data["custom_text"] = None
    data["custom_file_id"] = None
    data["detail"] = None
    data["details"] = []
    return data


def apply_custom_scene(data: dict, *, text: str | None = None, file_id: str | None = None) -> dict:
    """Своя сцена тоже сбрасывает деталь прошлой локации."""
    data["scene_id"] = None
    data["custom_text"] = text
    data["custom_file_id"] = file_id
    data["detail"] = None
    data["details"] = []
    return data


def request_from_state(user_id: int, data: dict, tier: str) -> GenerationRequest:
    people = list(data.get("people") or [])
    actors = list(data.get("actors") or [])
    named = [{"name": item["name"], "files": list(item.get("files") or [])} for item in data.get("named") or []]
    role = data.get("self_role")
    insert_prompt = None
    edit = bool(data.get("edit_mode"))
    base_id = data.get("edit_base_id")
    # «Улучши качество» — отдельная просьба по текущему кадру, не стопка деталей.
    detail = data.get("_quality_detail") or data.get("detail")
    pending = data.get("pending_insert")
    if pending:
        # Вписываем в последний кадр. Прошлая текстовая деталь уже внутри этого кадра.
        edit = True
        base_id = data.get("last_generation_id")
        detail = None
        if pending["kind"] == "self":
            people.append(pending["file_id"])
            role = pending["role"]
            insert_prompt = INSERT_SELF[pending["role"]]
        elif pending["kind"] == "actor":
            actors.append(pending["actor_id"])
            insert_prompt = insert_actor_prompt(pending["name"])
        else:
            named.append({"name": pending["name"], "files": list(pending.get("files") or [])})
            insert_prompt = insert_actor_prompt(pending["name"])
    return GenerationRequest(
        user_id=user_id,
        people_file_ids=people,
        actor_ids=actors,
        named_actors=[(item["name"], item["files"]) for item in named],
        self_role=role,
        scene_id=data.get("scene_id"),
        custom_scene_text=data.get("custom_text"),
        custom_scene_file_id=data.get("custom_file_id"),
        detail=detail,
        tier=tier,
        insert_prompt=insert_prompt,
        edit_mode=edit,
        base_generation_id=base_id,
    )
