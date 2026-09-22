import pytest

from services.generation import content_filter
from services.generation.prompt_builder import SAFETY_CLAUSE, ActorInput, GenerationInput, build


def test_content_filter():
    assert content_filter.is_allowed("зимой, в пальто")
    assert content_filter.is_allowed("on a beach at sunset")
    assert not content_filter.is_allowed("без одежды")
    assert not content_filter.is_allowed("Nude on the bed")
    assert not content_filter.is_allowed("ГОЛЫЕ на пляже")
    assert content_filter.is_allowed("on the grass near a zebra, no strah")
    assert content_filter.is_allowed("страх и класс")


def _inp(people=1, actors=1, scene_ref=None, detail=None):
    return GenerationInput(
        people=[f"p{i}" for i in range(people)],
        actors=[ActorInput(f"Actor{i}", f"desc{i}", [f"a{i}_0", f"a{i}_1"]) for i in range(actors)],
        scene_prompt="on a yacht",
        scene_ref=scene_ref,
        detail=detail,
        width=832,
        height=1248,
    )


def test_prompt_one_person_one_actor():
    prompt, refs = build(_inp(), max_refs=4)
    assert refs == ["p0", "a0_0", "a0_1"]
    assert "Image 1 is person A." in prompt
    assert "Image 2 shows actor Actor0 (desc0)." in prompt
    assert "Image 3 also shows actor Actor0." in prompt
    assert "A together with Actor0 on a yacht" in prompt
    assert SAFETY_CLAUSE in prompt


def test_refs_truncated_by_priority_scene_dropped_on_base():
    prompt, refs = build(_inp(people=2, actors=2, scene_ref="s"), max_refs=4)
    assert refs == ["p0", "p1", "a0_0", "a1_0"]
    assert "setting" not in prompt
    assert "A, B together with Actor0 and Actor1 on a yacht" in prompt


def test_scene_ref_included_on_premium_and_detail_appended():
    prompt, refs = build(_inp(people=2, actors=2, scene_ref="s", detail="in winter coats"), max_refs=14)
    assert refs == ["p0", "p1", "a0_0", "a1_0", "s", "a0_1", "a1_1"]
    assert "Image 5 shows the setting; place them in this exact setting." in prompt
    assert prompt.rstrip().endswith("in winter coats.")


def test_content_filter_no_false_positives_on_common_words():
    assert content_filter.is_allowed("мяч не смог попасть в ворота, попадание было точным")
    assert content_filter.is_allowed("killer whale documentary")
    assert not content_filter.is_allowed("голая попа")
    assert not content_filter.is_allowed("kill him")


def test_build_validates_cardinality():
    inp = _inp()
    inp.people = ["p0", "p1", "p2"]
    with pytest.raises(ValueError):
        build(inp, max_refs=14)
    inp = _inp()
    inp.actors = []
    with pytest.raises(ValueError):
        build(inp, max_refs=14)
    inp = _inp()
    inp.actors[0].refs = []
    with pytest.raises(ValueError):
        build(inp, max_refs=14)
    with pytest.raises(ValueError):
        build(_inp(people=2, actors=2), max_refs=3)
