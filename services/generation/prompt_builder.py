from dataclasses import dataclass

SAFETY_CLAUSE = (
    "Keep the face and the body build exactly as in the person and actor reference images: "
    "proportions, shoulders, torso, muscles and tattoos. "
    "Do not copy clothes, props or background from the person and actor photos. "
    "Clothing, pose and setting come from the scene description and the requested detail. "
    "A location reference is the exception: follow its framing, pose and place, but not the faces in it."
)
REALISM_CLAUSE = (
    "Natural skin texture with pores, realistic lighting and shadows, "
    "true-to-life proportions, tack-sharp high-resolution DSLR photograph, not a render and not a soft preview. "
    "Anatomically correct bodies: each person has exactly two arms, two hands and five fingers on each hand, "
    "no extra limbs, no fused or duplicated body parts."
)

# Просьба «просто сделать чётче»: модель иначе перерисовывает кадр целиком.
_QUALITY_HINTS = (
    "улучш", "качество", "разрешен", "четче", "резче",
    "sharpen", "higher quality", "upscale", "more detail",
)


def is_quality_request(detail: str) -> bool:
    low = (detail or "").lower().replace("ё", "е")
    return any(hint in low for hint in _QUALITY_HINTS)
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


def _ordered_refs(inp: GenerationInput) -> list[tuple[str, str, int]]:
    """Returns (kind, data, actor_index) in priority order."""
    out: list[tuple[str, str, int]] = []
    for i, p in enumerate(inp.people):
        out.append(("person", p, i))
    for i, a in enumerate(inp.actors):
        if a.refs:
            out.append(("actor_primary", a.refs[0], i))
    locs = list(inp.scene_refs or [])
    if not locs and inp.scene_ref:
        locs = [inp.scene_ref]
    for i, ref in enumerate(locs):
        out.append(("scene", ref, i))
    for i, a in enumerate(inp.actors):
        for r in a.refs[1:]:
            out.append(("actor_extra", r, i))
    return out


def _validate(inp: GenerationInput, budget: int) -> None:
    """`budget` — сколько слотов референсов доступно под людей и актёров."""
    if not 1 <= len(inp.people) <= len(PERSON_LABELS):
        raise ValueError(f"people must be 1..{len(PERSON_LABELS)}, got {len(inp.people)}")
    if not inp.actors:
        raise ValueError("at least one actor is required")
    # Имя без фото слот не занимает: лицо тогда держится только на тексте.
    needed = len(inp.people) + sum(1 for a in inp.actors if a.refs)
    if budget < needed:
        raise ValueError("max_refs too small for people + primary actor refs")


def _ref_lines(inp: GenerationInput, ordered: list[tuple[str, str, int]], start: int) -> list[str]:
    """Строки «кто есть кто» для референсов; нумерация с `start`."""
    lines: list[str] = []
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
            lines.append(
                f"Image {n} also shows actor {inp.actors[idx].name}. Another view of the same face and body."
            )
        elif kind == "scene":
            if idx == 0:
                lines.append(
                    f"Image {n} is a location reference. Match its framing, place and props. "
                    "Do not copy the faces or any extra person who appears only in it. "
                    "Do not replace the actor with a different man."
                )
            else:
                lines.append(
                    f"Image {n} is another reference for this scene. Follow its framing and place. "
                    "Do not copy faces. Do not replace the actor with a different man."
                )
    return lines


def build(inp: GenerationInput, max_refs: int) -> tuple[str, list[str]]:
    _validate(inp, max_refs)
    ordered = _ordered_refs(inp)[:max_refs]
    people = ", ".join(PERSON_LABELS[: len(inp.people)])
    actors = " and ".join(a.name for a in inp.actors)
    # Сначала главное — сцена и деталь пользователя, затем кто есть кто на референсах.
    lines: list[str] = [f"A candid photorealistic photo of {people} together with {actors} {inp.scene_prompt.strip()}."]
    if inp.cast_note:
        lines.append(inp.cast_note.strip().rstrip(".") + ".")
    lines.append(f"Exactly {len(inp.people) + len(inp.actors)} people in the frame, no other people in focus.")
    if inp.detail:
        lines.append(
            "Requested change, apply it fully even if it replaces the outfit or the pose: "
            + inp.detail.strip().rstrip(".") + "."
        )
    lines.extend(_ref_lines(inp, ordered, start=1))
    lines.append(SAFETY_CLAUSE)
    lines.append(REALISM_CLAUSE)
    return " ".join(lines), [d for _k, d, _i in ordered]


def build_edit(inp: GenerationInput, previous_image: str, detail: str, max_refs: int) -> tuple[str, list[str]]:
    """Дорисовка на уже готовом кадре. Предыдущее фото всегда refs[0].

    Сцену и лишние референсы актёра сюда не кладём: из-за них модель
    собирает новый кадр (карточки, другая одежда) вместо правки.
    Просьба улучшить качество не меняет содержимое — только резкость.
    """
    if not previous_image:
        raise ValueError("previous_image is required for an edit")
    if not (detail or "").strip():
        raise ValueError("detail is required for an edit")
    _validate(inp, max_refs - 1)
    if is_quality_request(detail):
        lines = [
            "Image 1 is the finished photo. Make this same photo sharper and more detailed. "
            "Do not change faces, clothes, pose, background, framing, objects or the number of people. "
            "Do not redraw the scene. Only increase sharpness and fine detail.",
            REALISM_CLAUSE,
        ]
        return " ".join(lines), [previous_image]
    # Первичное фото актёра — лицо и телосложение. Сцена и запасные ракурсы уводят кадр.
    ordered = [item for item in _ordered_refs(inp) if item[0] in ("person", "actor_primary")]
    ordered = ordered[: max_refs - 1]
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
    return " ".join(lines), [previous_image] + [d for _k, d, _i in ordered]


def build_insert(inp: GenerationInput, previous_image: str, instruction: str, max_refs: int) -> tuple[str, list[str]]:
    """Вписать ещё одного человека в готовый кадр, не собирая сцену заново."""
    if not previous_image:
        raise ValueError("previous_image is required for an insert")
    if not (instruction or "").strip():
        raise ValueError("instruction is required for an insert")
    _validate(inp, max_refs - 1)
    ordered = [item for item in _ordered_refs(inp) if item[0] in ("person", "actor_primary")]
    ordered = ordered[: max_refs - 1]
    lines = [
        "Image 1 is the finished photo. Edit that exact photo.",
        instruction.strip().rstrip(".") + ".",
        "Other images keep the same face and the same body build. Ignore clothes, props and background in them.",
    ]
    lines.extend(_ref_lines(inp, ordered, start=2))
    lines.append(SAFETY_CLAUSE)
    lines.append(REALISM_CLAUSE)
    return " ".join(lines), [previous_image] + [d for _k, d, _i in ordered]
