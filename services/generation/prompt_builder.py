from __future__ import annotations

from dataclasses import dataclass

SAFETY_CLAUSE = (
    "Keep the face and the body build exactly as in the reference images. No new tattoos. "
    "Each person keeps their own two arms and two legs. Five separate fingers, hands on the wrists. "
    "Do not move one person's arms onto another. Her limbs do not fuse with the man. "
    "Do not copy clothes, props, background, logos or text from the photos. "
    "Change only the clothes and the place. A location photo is only the place."
)
REALISM_CLAUSE = (
    "Natural skin texture with pores, realistic lighting and shadows, "
    "true-to-life proportions, tack-sharp high-resolution DSLR photograph, not a render and not a soft preview. "
    "Correct joints: elbows, wrists, knees and ankles bend the normal way. "
    "Bodies do not merge or share a limb."
)

# bytedance:seedream@4.5 отклоняет positivePrompt длиннее этого и кристалл возвращается.
PROMPT_MAX_CHARS = 3000
# SDXL смотрит только в начало промпта: оба текстовых энкодера держат около 75 токенов.
# Хвост с «Image 1 is…» модель просто не читает, поэтому для неё сцена стоит первой и коротко.
SDXL_PROMPT_MAX_CHARS = 420
SDXL_LEAD = (
    "raw photo, candid photograph, identical face, same person, "
    "do not change the face, natural skin pores, sharp focus"
)
NEGATIVE_PROMPT = (
    "cartoon, anime, illustration, painting, 3d render, cgi, plastic skin, doll, "
    "different face, changed face, another person, "
    "extra arm, third arm, extra hand, extra finger, six fingers, missing finger, "
    "fused fingers, melted hand, disconnected limb, floating hand, "
    "broken elbow, broken wrist, broken knee, merged bodies, duplicate torso, "
    "deformed, blurry, watermark, text, logo, collage, duplicate person"
)
# Сцена без актёра в кадре. Префикс снимается и в промпт модели не попадает.
_SOLO_MARK = "[solo]"

# Просьба «просто сделать чётче»: модель иначе перерисовывает кадр целиком.
_QUALITY_HINTS = (
    "улучш", "качество", "разрешен", "четче", "резче",
    "sharpen", "higher quality", "upscale", "more detail",
)


def is_quality_request(detail: str) -> bool:
    low = (detail or "").lower().replace("ё", "е")
    return any(hint in low for hint in _QUALITY_HINTS)


def scene_is_solo(scene_prompt: str) -> bool:
    return (scene_prompt or "").lstrip().startswith(_SOLO_MARK)


def _clothes_come_off(scene: str) -> bool:
    """Кнопка «снять» просит убрать одежду с фото, а не заменить её другим комплектом."""
    low = (scene or "").lower()
    return "remove the clothes" in low or "completely naked" in low


def scene_text(scene_prompt: str) -> str:
    text = (scene_prompt or "").strip()
    if text.startswith(_SOLO_MARK):
        text = text[len(_SOLO_MARK):].strip()
    return text


def _clip_sdxl(parts: list[str]) -> str:
    """Короткий промпт: сцена в начале, лишнее обрезается с хвоста."""
    text = ", ".join(part.strip().strip(".,") for part in parts if part and part.strip())
    if len(text) <= SDXL_PROMPT_MAX_CHARS:
        return text
    cut = text[:SDXL_PROMPT_MAX_CHARS].rsplit(" ", 1)[0]
    return cut or text[:SDXL_PROMPT_MAX_CHARS]


def _people_count(inp: GenerationInput, solo: bool) -> int | None:
    if solo:
        return len(inp.people)
    if inp.actors:
        return len(inp.people) + len(inp.actors)
    return None


def _sdxl_fresh(inp: GenerationInput) -> str:
    solo = scene_is_solo(inp.scene_prompt)
    parts = [SDXL_LEAD, scene_text(inp.scene_prompt)]
    if not solo and inp.actors:
        parts.append("with " + " and ".join(a.name for a in inp.actors))
    if inp.cast_note:
        parts.append(inp.cast_note)
    if inp.detail:
        parts.append(inp.detail)
    count = _people_count(inp, solo)
    if count is not None:
        word = "person" if count == 1 else "people"
        parts.append(f"exactly {count} {word}")
    return _clip_sdxl(parts)


def _sdxl_edit(detail: str) -> str:
    if is_quality_request(detail):
        return _clip_sdxl([
            "raw photo, the same photograph, sharper, more fine detail",
            "same faces, same clothes, same pose, same place",
        ])
    return _clip_sdxl([
        "raw photo, the same photograph, identical face, do not change the face",
        "same people, same clothes except the requested change, same place, same framing",
        detail,
    ])


def _sdxl_insert(instruction: str) -> str:
    return _clip_sdxl([
        "raw photo, the same photograph, add exactly one new person",
        instruction,
        "keep everyone already in the photo, same clothes, same place",
    ])


def sdxl_adapter_groups(inp: GenerationInput, max_refs: int, mode: str) -> list[tuple[str, list[str]]]:
    """Группы для IP-Adapter: одно лицо на человека, место отдельно.

    В адаптер уходит одно главное фото лица. Усреднение ракурсов размывает личность.
    Кадр локации в этот список не кладём в запрос: он перетягивает людей.
    """
    if mode == "insert":
        ordered = _insert_face_refs(inp)[: max_refs - 1]
        include_place = False
    elif mode == "edit":
        keep = ("person",) if scene_is_solo(inp.scene_prompt) else ("person", "actor_primary")
        ordered = [item for item in _ordered_refs(inp) if item[0] in keep][: max_refs - 1]
        include_place = False
    else:
        ordered = _ordered_refs(inp)
        if scene_is_solo(inp.scene_prompt):
            ordered = _without_actors(ordered)
        ordered = ordered[:max_refs]
        include_place = True
    faces: dict[tuple[str, int], list[str]] = {}
    order: list[tuple[str, int]] = []
    places: list[str] = []
    for kind, data, idx in ordered:
        if kind == "scene":
            places.append(data)
            continue
        key = ("person", idx) if kind == "person" else ("actor", idx)
        if key not in faces:
            order.append(key)
            faces[key] = [data]
    groups = [("face", faces[key]) for key in order]
    if include_place and places:
        groups.append(("place", places[:1]))
    return groups


def _join(lines: list[str]) -> str:
    """Seedream отвергает промпт длиннее 3000 символов, генерация падает и кристалл возвращается."""
    text = " ".join(line.strip() for line in lines if line and line.strip())
    if len(text) <= PROMPT_MAX_CHARS:
        return text
    shorter = [ln for ln in lines if ln != REALISM_CLAUSE]
    text = " ".join(line.strip() for line in shorter if line and line.strip())
    if len(text) <= PROMPT_MAX_CHARS:
        return text
    clipped = text[:PROMPT_MAX_CHARS]
    cut = clipped.rfind(" ")
    return clipped[:cut] if cut > 2500 else clipped


PERSON_LABELS = ["A", "B"]


@dataclass
class ActorInput:
    name: str
    description: str
    refs: list[str]  # refs[0] is primary


@dataclass
class GenerationInput:
    people: list[str]
    actors: list[ActorInput]
    scene_prompt: str
    scene_ref: str | None
    detail: str | None
    width: int
    height: int
    # Как человек с фото пользователя ведёт себя в новом кадре. Правка детали его не трогает.
    cast_note: str | None = None
    # Несколько кадров локации. Пусто — берётся один scene_ref.
    scene_refs: list[str] | None = None
    # Кого вписываем в готовый кадр: person / actor / named. Чужие фото не прикладываем.
    insert_target: str | None = None
    insert_actor_index: int | None = None


def _ordered_refs(inp: GenerationInput) -> list[tuple[str, str, int]]:
    """Люди, затем лица актёров, локация в конце.

    Иначе восемь кадров площадки вытесняют фото Видаля, и модель рисует
    второго Сиффреди и человека из референса локации.
    """
    out: list[tuple[str, str, int]] = []
    for i, p in enumerate(inp.people):
        out.append(("person", p, i))
    extras: list[list[tuple[str, str, int]]] = []
    for i, a in enumerate(inp.actors):
        if not a.refs:
            continue
        out.append(("actor_primary", a.refs[0], i))
        extras.append([("actor_extra", r, i) for r in a.refs[1:]])
    # По одному дополнительному ракурсу каждому, чтобы первый актёр не забрал все слоты.
    while any(extras):
        nxt: list[list[tuple[str, str, int]]] = []
        for bucket in extras:
            out.append(bucket[0])
            if bucket[1:]:
                nxt.append(bucket[1:])
        extras = nxt
    locs = list(inp.scene_refs or [])
    if not locs and inp.scene_ref:
        locs = [inp.scene_ref]
    for i, ref in enumerate(locs):
        out.append(("scene", ref, i))
    return out


def _validate(inp: GenerationInput, budget: int) -> None:
    """`budget` — сколько слотов референсов доступно под людей и актёров."""
    if not 1 <= len(inp.people) <= len(PERSON_LABELS):
        raise ValueError(f"people must be 1..{len(PERSON_LABELS)}, got {len(inp.people)}")
    # Пустой список актёров — кадр только с девушкой с фото. Сцена сама решает, есть ли в ней мужчина.
    # Имя без фото слот не занимает: лицо тогда держится только на тексте.
    needed = len(inp.people) + sum(1 for a in inp.actors if a.refs)
    if budget < needed:
        raise ValueError("max_refs too small for people + primary actor refs")


_FIRST_SCENE = (
    "Image {n} is a location reference. Use its place and props only. "
    "Faces and bodies in it are blanked out. Do not copy the faces, bodies or clothes "
    "of any person who appears only in it, including a camera operator or crew. "
    "Do not replace an actor with a different man."
)
_NEXT_SCENE = (
    "Image {n} is another reference for this scene. Use its place and props. "
    "One room only: do not collage different places into one photo. "
    "Do not copy faces, bodies or clothes from it. Do not replace an actor with a different man."
)
# Восемь отдельных строк про кадры площадки раздували промпт за 3000 символов.
_MORE_SCENES = (
    "Images {a}-{b} are more references for this same place. Use their place and props. "
    "Do not copy faces, bodies, clothes or crew from them. Do not replace an actor with a different man."
)


def _image_list(nums: list[int]) -> str:
    if len(nums) == 1:
        return str(nums[0])
    if len(nums) == 2:
        return f"{nums[0]} and {nums[1]}"
    return ", ".join(str(n) for n in nums[:-1]) + f" and {nums[-1]}"


def _ref_lines(inp: GenerationInput, ordered: list[tuple[str, str, int]], start: int) -> list[str]:
    """Строки «кто есть кто» для референсов; нумерация с `start`."""
    lines: list[str] = []
    scene_ns: list[int] = []
    extra_groups: dict[int, list[int]] = {}
    for n, (kind, _data, idx) in enumerate(ordered, start=start):
        if kind == "actor_extra":
            extra_groups.setdefault(idx, []).append(n)
    seen_extra: set[int] = set()
    for n, (kind, _data, idx) in enumerate(ordered, start=start):
        if kind == "person":
            lines.append(f"Image {n} is person {PERSON_LABELS[idx]}.")
        elif kind == "actor_primary":
            a = inp.actors[idx]
            desc = f" ({a.description})" if a.description else ""
            lines.append(
                f"Image {n} shows actor {a.name}{desc}. Match the face and the body build, not the clothes."
            )
        elif kind == "actor_extra":
            group = extra_groups[idx]
            if len(group) == 1:
                lines.append(
                    f"Image {n} also shows actor {inp.actors[idx].name}. Another view of the same face and body."
                )
            elif idx not in seen_extra:
                seen_extra.add(idx)
                lines.append(
                    f"Images {_image_list(group)} also show actor {inp.actors[idx].name}. "
                    "More views of the same face and body."
                )
        elif kind == "scene":
            scene_ns.append(n)
    if scene_ns:
        lines.append(_FIRST_SCENE.format(n=scene_ns[0]))
        extra = scene_ns[1:]
        if len(extra) == 1:
            lines.append(_NEXT_SCENE.format(n=extra[0]))
        elif extra:
            lines.append(_MORE_SCENES.format(a=extra[0], b=extra[-1]))
    return lines


def _cast_lines(inp: GenerationInput) -> list[str]:
    """Несколько актёров — каждый со своим лицом. Имя без фото не получает чужое."""
    if len(inp.actors) < 2:
        return []
    names = ", ".join(a.name for a in inp.actors)
    lines = [
        f"Each actor appears exactly once: {names}. "
        "They are different people. Do not duplicate anyone and do not give two people the same face. "
        "Do not reuse one actor's face or body for another actor. "
        "The scene text describes the place and the clothes. It does not mean the actors share one face.",
    ]
    missing = [a for a in inp.actors if not a.refs]
    if missing:
        who = " and ".join(
            f"{a.name} ({a.description})" if a.description else a.name for a in missing
        )
        lines.append(
            f"{who} has no reference photo. "
            "Keep that person different from every actor who has a photo. Do not copy their face."
        )
    return lines


def _without_actors(ordered: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    return [item for item in ordered if item[0] not in ("actor_primary", "actor_extra")]


# Qwen-Image-Edit-Plus принимает 1–3 референса. Лишние ракурсы смешивают лица, поэтому их нет.
QWEN_MAX_REFS = 3


def _qwen_validate(inp: GenerationInput, slots: int) -> None:
    """Не отказывать, если людей больше, чем слотов: лишние фото просто не уйдут."""
    needed = len(inp.people) + sum(1 for a in inp.actors if a.refs)
    _validate(inp, max(slots, needed, 1))


def _location_refs(inp: GenerationInput) -> list[str]:
    locs = list(inp.scene_refs or [])
    if not locs and inp.scene_ref:
        locs = [inp.scene_ref]
    return locs


def _qwen_fresh_ordered(inp: GenerationInput, max_refs: int) -> list[tuple[str, str, int]]:
    """Фото пользователя, одно главное фото актёра, и место, если слот остался."""
    cap = min(max_refs, QWEN_MAX_REFS)
    ordered: list[tuple[str, str, int]] = [("person", photo, i) for i, photo in enumerate(inp.people)]
    if not scene_is_solo(inp.scene_prompt):
        for i, actor in enumerate(inp.actors):
            if actor.refs:
                ordered.append(("actor_primary", actor.refs[0], i))
    locs = _location_refs(inp)
    if locs and len(ordered) < cap:
        ordered.append(("scene", locs[0], 0))
    return ordered[:cap]


def _qwen_ref_lines(inp: GenerationInput, ordered: list[tuple[str, str, int]], start: int) -> list[str]:
    lines: list[str] = []
    for n, (kind, _data, idx) in enumerate(ordered, start=start):
        if kind == "person":
            if n == 1:
                continue
            lines.append(
                f"Reference image {n} is person {PERSON_LABELS[idx]}. "
                "Use only this face and body, not the clothes or the background."
            )
        elif kind == "actor_primary":
            lines.append(
                f"Reference image {n} is {inp.actors[idx].name}. "
                "Use only this face and body, not the clothes or the background."
            )
        elif kind == "scene":
            lines.append(
                f"Reference image {n} is the place. "
                "Follow its room and framing, do not copy the people."
            )
    return lines


def _qwen_lead(inp: GenerationInput) -> str:
    if len(inp.people) <= 1:
        return (
            "Edit reference image 1. It is the photograph to change. "
            "Preserve the exact facial identity, age, skin tone, hair and body proportions of this person. "
            "Keep this person's face and pose."
        )
    return (
        "Edit reference image 1. It is the photograph to change. "
        "Preserve the exact facial identity, age, skin tone, hair and body proportions of these people. "
        "Keep their faces and poses."
    )


def _qwen_fresh(inp: GenerationInput, max_refs: int) -> tuple[str, list[str]]:
    solo = scene_is_solo(inp.scene_prompt)
    ordered = _qwen_fresh_ordered(inp, max_refs)
    scene = scene_text(inp.scene_prompt).rstrip(".").strip()
    lines = [_qwen_lead(inp), f"Make only this change: {scene}."]
    if inp.cast_note:
        lines.append(inp.cast_note.strip().rstrip(".") + ".")
    count = _people_count(inp, solo)
    if count is not None:
        word = "person" if count == 1 else "people"
        lines.append(f"Exactly {count} {word}.")
    elif not solo:
        lines.append(
            "If the scene mentions a man, he is a new person in this scene, not a second copy of her."
        )
    if not solo and len(inp.actors) >= 2:
        names = " and ".join(actor.name for actor in inp.actors)
        lines.append(f"Each actor appears exactly once: {names}. They are different people.")
    if inp.detail:
        lines.append("Also apply this change: " + inp.detail.strip().rstrip(".") + ".")
    lines.extend(_qwen_ref_lines(inp, ordered, start=1))
    return _join(lines), [data for _kind, data, _idx in ordered]


def _qwen_edit(
    inp: GenerationInput, previous_image: str, detail: str, max_refs: int,
) -> tuple[str, list[str]]:
    cap = min(max_refs, QWEN_MAX_REFS)
    keep = ("person",) if scene_is_solo(inp.scene_prompt) else ("person", "actor_primary")
    ordered = [item for item in _ordered_refs(inp) if item[0] in keep][: max(0, cap - 1)]
    lines = [
        "Edit reference image 1. Image 1 is the finished photo. "
        "Make only this change: " + detail.strip().rstrip(".") + ". "
        "Keep faces, clothes except the requested change, pose, place and framing.",
    ]
    lines.extend(_qwen_ref_lines(inp, ordered, start=2))
    return _join(lines), [previous_image] + [data for _kind, data, _idx in ordered]


def _qwen_insert(
    inp: GenerationInput, previous_image: str, instruction: str, ordered: list[tuple[str, str, int]],
) -> tuple[str, list[str]]:
    lines = [
        "Edit reference image 1. Image 1 is the finished photo. "
        "Add exactly one new person. Keep everyone already in the photo.",
        instruction.strip().rstrip(".") + ".",
    ]
    if ordered:
        kind, _data, idx = ordered[0]
        who = inp.actors[idx].name if kind == "actor_primary" else f"person {PERSON_LABELS[idx]}"
        lines.append(
            f"Reference image 2 is {who}. "
            "Use only this face and body, not the clothes or the background. "
            "Dress the new person to match the clothes already in image 1."
        )
    else:
        name = _inserted_name(inp)
        who = f"The new person is {name}. " if name else ""
        lines.append(
            who + "There is no reference photo of the new person. "
            "Do not copy a face already in image 1."
        )
    return _join(lines), [previous_image] + [data for _kind, data, _idx in ordered]


def _source_lead(people: int) -> str:
    """Обычное фото — правка исходного кадра, а не новый человек."""
    if people <= 1:
        opening = "Image 1 is the source photograph."
    else:
        opening = "The first images are the source photographs."
    return (
        f"{opening} Exact face and body from this photo. No new tattoos. "
        "Copy this skeleton: same pose, shoulders, elbows, wrists, hands, hips and knees. "
        "Two arms, two legs, five fingers. Bodies do not fuse."
    )


def build(inp: GenerationInput, max_refs: int, style: str = "instruct") -> tuple[str, list[str]]:
    if style == "qwen":
        _qwen_validate(inp, max_refs)
        return _qwen_fresh(inp, max_refs)
    _validate(inp, max_refs)
    ordered = _ordered_refs(inp)
    solo = scene_is_solo(inp.scene_prompt)
    if solo:
        # Актёр выбран в боте, но в эту сцену не встаёт и его фото модели не уходят.
        ordered = _without_actors(ordered)
    ordered = ordered[:max_refs]
    if style == "sdxl":
        return _sdxl_fresh(inp), [d for _k, d, _i in ordered]
    people = ", ".join(PERSON_LABELS[: len(inp.people)])
    scene = scene_text(inp.scene_prompt).rstrip(".").strip()
    # Сначала личность и исходный кадр: klein иначе рисует нового человека.
    lines = [_source_lead(len(inp.people))]
    if solo:
        lines.append(f"Only {people} is in the frame. {scene}.")
        count = len(inp.people)
    elif not inp.actors:
        if len(inp.people) == 1:
            lines.append(
                "Person A is the woman from the source photo. Keep her face, figure and appearance."
            )
        else:
            lines.append(
                f"{people} are the people from the source photos. Keep each face, figure and appearance."
            )
        lines.append(
            "If the scene mentions a man, he is a new person in this scene, not a second copy of her."
        )
        lines.append(f"{scene}.")
        count = None
    else:
        actors = " and ".join(a.name for a in inp.actors)
        lines.append(f"{people} together with {actors}. {scene}.")
        count = len(inp.people) + len(inp.actors)
    if inp.cast_note:
        lines.append(inp.cast_note.strip().rstrip(".") + ".")
    if count is not None:
        word = "person" if count == 1 else "people"
        lines.append(f"Exactly {count} {word} in the frame, no other people in focus.")
    if not solo:
        lines.extend(_cast_lines(inp))
    if inp.detail:
        lines.append(
            "Requested change, apply it fully even if it replaces the outfit or the pose: "
            + inp.detail.strip().rstrip(".") + "."
        )
    lines.extend(_ref_lines(inp, ordered, start=1))
    lines.append(SAFETY_CLAUSE)
    if _clothes_come_off(scene):
        lines.append(
            "The clothes from the source photo are removed. "
            "Do not replace them with another outfit."
        )
    lines.append(REALISM_CLAUSE)
    return _join(lines), [d for _k, d, _i in ordered]


def build_edit(
    inp: GenerationInput, previous_image: str, detail: str, max_refs: int, style: str = "instruct",
) -> tuple[str, list[str]]:
    """Дорисовка на уже готовом кадре. Предыдущее фото всегда refs[0].

    Сцену и лишние референсы актёра сюда не кладём: из-за них модель
    собирает новый кадр (карточки, другая одежда) вместо правки.
    Просьба улучшить качество не меняет содержимое — только резкость.
    """
    if not previous_image:
        raise ValueError("previous_image is required for an edit")
    if not (detail or "").strip():
        raise ValueError("detail is required for an edit")
    if style == "qwen":
        _qwen_validate(inp, max(max_refs - 1, 0))
    else:
        _validate(inp, max_refs - 1)
    if style == "sdxl" and is_quality_request(detail):
        return _sdxl_edit(detail), [previous_image]
    if is_quality_request(detail):
        lines = [
            "Image 1 is the finished photo. Make this same photo sharper and more detailed. "
            "Do not change faces, clothes, pose, background, framing, objects or the number of people. "
            "Do not redraw the scene. Only increase sharpness and fine detail.",
            REALISM_CLAUSE,
        ]
        return _join(lines), [previous_image]
    if style == "qwen":
        return _qwen_edit(inp, previous_image, detail, max_refs)
    # Первичное фото актёра — лицо и телосложение. Сцена и запасные ракурсы уводят кадр.
    # В сольной сцене актёра в кадре нет: его фото на правке вернуло бы его обратно.
    keep = ("person",) if scene_is_solo(inp.scene_prompt) else ("person", "actor_primary")
    ordered = [item for item in _ordered_refs(inp) if item[0] in keep]
    ordered = ordered[: max_refs - 1]
    if style == "sdxl":
        return _sdxl_edit(detail), [previous_image] + [d for _k, d, _i in ordered]
    lines: list[str] = [
        "Image 1 is the finished photo. Edit that exact photo. "
        "Keep the same people, faces, body build, framing, background, lighting and sharpness. "
        "Do not invent a new scene and do not add objects that were not requested.",
        "Apply only this change, and apply it fully: " + detail.strip().rstrip(".") + ".",
        "If the change is about clothes, hair or pose, change only that and leave the rest of the photo as it is.",
        "Other images keep the same face and the same body build. Ignore clothes, props and background in them.",
    ]
    lines.extend(_ref_lines(inp, ordered, start=2))
    lines.append(SAFETY_CLAUSE)
    lines.append(REALISM_CLAUSE)
    return _join(lines), [previous_image] + [d for _k, d, _i in ordered]


def _insert_face_refs(inp: GenerationInput) -> list[tuple[str, str, int]]:
    """Только лицо того, кого добавляем.

    Фото жены и актёров, которые уже стоят в кадре, модель копирует ещё раз:
    так вместо Видаля появлялся второй Сиффреди.
    """
    if inp.insert_target == "person":
        if not inp.people:
            raise ValueError("insert needs the new person's photo")
        idx = len(inp.people) - 1
        return [("person", inp.people[idx], idx)]
    if inp.insert_target in ("actor", "named"):
        idx = inp.insert_actor_index
        if idx is None or not 0 <= idx < len(inp.actors):
            raise ValueError("insert_actor_index is required")
        actor = inp.actors[idx]
        if not actor.refs:
            return []
        ordered = [("actor_primary", actor.refs[0], idx)]
        ordered += [("actor_extra", ref, idx) for ref in actor.refs[1:]]
        return ordered
    raise ValueError("insert_target is required")


def _inserted_name(inp: GenerationInput) -> str:
    idx = inp.insert_actor_index
    if idx is None or not 0 <= idx < len(inp.actors):
        return ""
    return inp.actors[idx].name


def build_insert(
    inp: GenerationInput, previous_image: str, instruction: str, max_refs: int, style: str = "instruct",
) -> tuple[str, list[str]]:
    """Вписать ещё одного человека в готовый кадр, не собирая сцену заново."""
    if not previous_image:
        raise ValueError("previous_image is required for an insert")
    if not (instruction or "").strip():
        raise ValueError("instruction is required for an insert")
    if style == "qwen":
        _qwen_validate(inp, max(max_refs - 1, 0))
        # Только первое фото нового человека. Запасные ракурсы Квен смешивает с теми, кто уже в кадре.
        room = 1 if min(max_refs, QWEN_MAX_REFS) > 1 else 0
        return _qwen_insert(inp, previous_image, instruction, _insert_face_refs(inp)[:room])
    if style == "sdxl":
        # В адаптер уходит одно новое лицо. Проверка всего состава здесь не нужна:
        # фото тех, кто уже в кадре, модель копирует второй раз.
        ordered = _insert_face_refs(inp)[:1]
        return _sdxl_insert(instruction), [previous_image] + [d for _k, d, _i in ordered]
    # В референсы идёт только новый человек. Проверка всего состава здесь роняет
    # кадр, где жена и актёры уже стоят: их фото модель копирует второй раз.
    ordered = _insert_face_refs(inp)[: max(max_refs - 1, 0)]
    lines = [
        "Image 1 is the finished photo. Edit that exact photo.",
        instruction.strip().rstrip(".") + ".",
        "Add exactly one new person. Do not duplicate anyone already in image 1 "
        "and do not replace them with a different face. "
        "Keep the faces, expression, clothes, pose, framing and background of everyone already in the photo. "
        "Do not invent extra people.",
    ]
    if ordered:
        lines.append(
            "The new person's face and body build come from the later images. "
            "Do not copy the clothes or the nudity from those images. "
            "Dress the new person to match the clothes already in image 1. "
            "Do not undress anyone."
        )
        lines.extend(_ref_lines(inp, ordered, start=2))
    else:
        name = _inserted_name(inp)
        who = f"The new person is {name}. " if name else ""
        lines.append(
            who + "There is no reference photo of the new person. "
            "Do not copy a face already in image 1."
        )
    lines.append(SAFETY_CLAUSE)
    lines.append(REALISM_CLAUSE)
    lines.append(
        "Clothes already in image 1 win. The new person wears clothes that match this photo. "
        "Do not copy outfits or bare skin from the later images."
    )
    return _join(lines), [previous_image] + [d for _k, d, _i in ordered]
