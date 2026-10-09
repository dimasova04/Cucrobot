from aiogram.fsm.state import State, StatesGroup

from bot import texts
from services.billing import subscriptions
from services.generation.content_filter import is_allowed, mentions_minor
from services.video.prompts import VIDEO_PROMPT_MAX
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
    video_prompt = State()


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
    }


def norm_name(name: str) -> str:
    return " ".join((name or "").strip().lower().replace("ё", "е").split())


INSERT_SELF = {
    "watch": (
        "Add person B into this exact photo. He stands nearby and only watches the people already there. "
        "He does not touch them. Keep the same faces, expression, clothes, pose, framing and background. "
        "Dress him to match the clothes already in this photo. Do not undress anyone. Do not redraw the scene."
    ),
    "join": (
        "Add person B into this exact photo beside the people already there. "
        "Keep the same faces, expression, clothes, pose, framing and background of everyone already in the photo. "
        "Dress him to match the clothes already in this photo. Do not undress anyone. Do not redraw the scene."
    ),
}


def insert_actor_prompt(name: str) -> str:
    return (
        f"Add {name} into this exact photo beside the people already there. "
        f"{name} is the only new person. Do not add another copy of anyone already in the photo. "
        "Keep the same faces, expression, clothes, pose, framing and background of everyone already in the photo. "
        "Dress the new person to match the clothes already in this photo. "
        "Do not copy clothes or nudity from the reference photos. Do not undress anyone. Do not redraw the scene."
    )


def effective_tier(user) -> str:
    """Качество пользователя из профиля, с даунгрейдом до base без активной подписки."""
    tier = getattr(user, "preferred_tier", None) or "base"
    if tier == "premium" and not subscriptions.is_active(user):
        return "base"
    return tier


DETAIL_MAX_LEN = 300


def validate_detail(text: str) -> str | None:
    if len(text) > DETAIL_MAX_LEN:
        return texts.DETAIL_TOO_LONG
    if not is_allowed(text):
        return texts.TEXT_REJECTED
    return None


def validate_video_prompt(text: str) -> str | None:
    """Свой текст видео. Длину почти не режем, взрослые слова проходят. Детей нет."""
    cleaned = (text or "").strip()
    if not cleaned:
        return texts.VIDEO_PROMPT_EMPTY
    if len(cleaned) > VIDEO_PROMPT_MAX:
        return texts.VIDEO_PROMPT_TOO_LONG
    if mentions_minor(cleaned):
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


def drop_added_people(data: dict) -> None:
    """Новая сцена начинается с актёра, выбранного на старте.

    Кого вписали потом — второго актёра, названное имя или себя — в этот кадр не берём.
    """
    if "base_actors" in data or "base_named" in data:
        data["actors"] = list(data.get("base_actors") or [])
        data["named"] = [
            {"name": item["name"], "files": list(item.get("files") or [])}
            for item in (data.get("base_named") or [])
        ]
    elif data.get("actors"):
        data["actors"] = list(data["actors"][:1])
        data["named"] = []
    elif data.get("named"):
        data["actors"] = []
        first = data["named"][0]
        data["named"] = [{"name": first["name"], "files": list(first.get("files") or [])}]
    people = data.get("people")
    if people:
        data["people"] = list(people[:1])
    data["self_file_id"] = None
    data["self_role"] = None
    data.pop("pending_insert", None)


def apply_catalog_scene(data: dict, scene_id: int) -> dict:
    """Новая сцена из каталога — свежий кадр: прошлая деталь и добавленные люди не переносятся."""
    drop_added_people(data)
    data["scene_id"] = scene_id
    data["custom_text"] = None
    data["custom_file_id"] = None
    data["detail"] = None
    return data


def apply_custom_scene(data: dict, *, text: str | None = None, file_id: str | None = None) -> dict:
    """Своя сцена тоже сбрасывает деталь и людей, добавленных в прошлый кадр."""
    drop_added_people(data)
    data["scene_id"] = None
    data["custom_text"] = text
    data["custom_file_id"] = file_id
    data["detail"] = None
    return data


def request_from_state(user_id: int, data: dict, tier: str) -> GenerationRequest:
    people = list(data.get("people") or [])
    actors = list(data.get("actors") or [])
    named = [{"name": item["name"], "files": list(item.get("files") or [])} for item in data.get("named") or []]
    role = data.get("self_role")
    insert_prompt = None
    insert_target = None
    edit = bool(data.get("edit_mode"))
    base_id = data.get("edit_base_id")
    detail = data.get("detail")
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
            insert_target = "person"
        elif pending["kind"] == "actor":
            actors.append(pending["actor_id"])
            insert_prompt = insert_actor_prompt(pending["name"])
            insert_target = "actor"
        else:
            named.append({"name": pending["name"], "files": list(pending.get("files") or [])})
            insert_prompt = insert_actor_prompt(pending["name"])
            insert_target = "named"
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
        insert_target=insert_target,
        edit_mode=edit,
        base_generation_id=base_id,
    )
