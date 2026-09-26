from dataclasses import dataclass

SAFETY_CLAUSE = (
    "Keep every face exactly as in the reference images. "
    "Everyone is fully clothed, outfits fit the scene."
)
REALISM_CLAUSE = (
    "Natural skin texture with pores, realistic lighting and shadows, "
    "true-to-life proportions, looks like a real DSLR photograph, not a render."
)
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


def _ordered_refs(inp: GenerationInput) -> list[tuple[str, str, int]]:
    """Returns (kind, data, actor_index) in priority order."""
    out: list[tuple[str, str, int]] = []
    for i, p in enumerate(inp.people):
        out.append(("person", p, i))
    for i, a in enumerate(inp.actors):
        if a.refs:
            out.append(("actor_primary", a.refs[0], i))
    if inp.scene_ref:
        out.append(("scene", inp.scene_ref, -1))
    for i, a in enumerate(inp.actors):
        for r in a.refs[1:]:
            out.append(("actor_extra", r, i))
    return out


def build(inp: GenerationInput, max_refs: int) -> tuple[str, list[str]]:
    if not 1 <= len(inp.people) <= len(PERSON_LABELS):
        raise ValueError(f"people must be 1..{len(PERSON_LABELS)}, got {len(inp.people)}")
    if not inp.actors:
        raise ValueError("at least one actor is required")
    for a in inp.actors:
        if not a.refs:
            raise ValueError(f"actor {a.name!r} has no reference images")
    if max_refs < len(inp.people) + len(inp.actors):
        raise ValueError("max_refs too small for people + primary actor refs")
    ordered = _ordered_refs(inp)[:max_refs]
    people = ", ".join(PERSON_LABELS[: len(inp.people)])
    actors = " and ".join(a.name for a in inp.actors)
    # Сначала главное — сцена и деталь пользователя, затем кто есть кто на референсах.
    lines: list[str] = [f"A candid photorealistic photo of {people} together with {actors} {inp.scene_prompt.strip()}."]
    if inp.detail:
        lines.append(inp.detail.strip().rstrip(".") + ".")
    for n, (kind, _data, idx) in enumerate(ordered, start=1):
        if kind == "person":
            lines.append(f"Image {n} is person {PERSON_LABELS[idx]}.")
        elif kind == "actor_primary":
            a = inp.actors[idx]
            desc = f" ({a.description})" if a.description else ""
            lines.append(f"Image {n} shows actor {a.name}{desc}.")
        elif kind == "actor_extra":
            lines.append(f"Image {n} also shows actor {inp.actors[idx].name}.")
        elif kind == "scene":
            lines.append(f"Image {n} shows the setting; place them in this exact setting.")
    lines.append(SAFETY_CLAUSE)
    lines.append(REALISM_CLAUSE)
    return " ".join(lines), [d for _k, d, _i in ordered]
