import pytest

from services.generation import content_filter
from services.generation.prompt_builder import (
    REALISM_CLAUSE, SAFETY_CLAUSE, ActorInput, GenerationInput, build, build_edit, build_insert,
)


def test_content_filter():
    assert content_filter.is_allowed("зимой, в пальто")
    assert content_filter.is_allowed("on a beach at sunset")
    assert not content_filter.is_allowed("без одежды")
    assert not content_filter.is_allowed("Nude on the bed")
    assert not content_filter.is_allowed("ГОЛЫЕ на пляже")
    assert content_filter.is_allowed("on the grass near a zebra, no strah")
    assert content_filter.is_allowed("страх и класс")


def _inp(people=1, actors=1, scene_ref=None, scene_refs=None, detail=None):
    return GenerationInput(
        people=[f"p{i}" for i in range(people)],
        actors=[ActorInput(f"Actor{i}", f"desc{i}", [f"a{i}_0", f"a{i}_1"]) for i in range(actors)],
        scene_prompt="on a yacht",
        scene_ref=scene_ref,
        detail=detail,
        scene_refs=scene_refs,
        width=832,
        height=1248,
    )


def test_prompt_one_person_one_actor():
    prompt, refs = build(_inp(), max_refs=4)
    assert refs == ["p0", "a0_0", "a0_1"]
    assert prompt.startswith("A candid photorealistic photo of A together with Actor0 on a yacht.")
    assert "Exactly 2 people in the frame, no other people in focus." in prompt
    assert "Image 1 is person A." in prompt
    assert "Image 2 shows actor Actor0 (desc0)." in prompt
    assert "Image 3 also shows actor Actor0." in prompt
    assert "body build" in prompt
    assert "not the clothes" in prompt
    assert "A together with Actor0 on a yacht" in prompt
    assert SAFETY_CLAUSE in prompt


def test_refs_truncated_by_priority_scene_dropped_on_base():
    prompt, refs = build(_inp(people=2, actors=2, scene_ref="s"), max_refs=4)
    assert refs == ["p0", "p1", "a0_0", "a1_0"]
    assert "is a location reference" not in prompt
    assert "A, B together with Actor0 and Actor1 on a yacht" in prompt


def test_scene_ref_included_on_premium_and_detail_appended():
    prompt, refs = build(_inp(people=2, actors=2, scene_ref="s", detail="in winter coats"), max_refs=14)
    # Лица актёров раньше локации: иначе лишние кадры площадки вытесняют второго актёра.
    assert refs == ["p0", "p1", "a0_0", "a1_0", "a0_1", "a1_1", "s"]
    assert "Image 7 is a location reference. Match its framing, place and props." in prompt
    assert "Do not replace an actor with a different man." in prompt
    assert "camera operator or crew" in prompt
    assert "Each actor appears exactly once: Actor0, Actor1." in prompt
    assert "Requested change, apply it fully even if it replaces the outfit or the pose: in winter coats." in prompt
    assert prompt.index("in winter coats.") < prompt.index("Image 1 is person A.")


def test_several_location_refs_do_not_replace_faces():
    prompt, refs = build(_inp(scene_refs=["s1", "s2"]), max_refs=14)
    assert refs[:5] == ["p0", "a0_0", "a0_1", "s1", "s2"]
    assert "another reference for this scene" in prompt
    assert "Do not copy the faces, bodies or clothes" in prompt
    assert "Do not copy faces, bodies or clothes from it." in prompt


def test_actor_photos_are_kept_when_the_location_has_many_frames():
    """Сиффреди, Синс без фото и Видаль на площадке из восьми кадров.

    Раньше локация занимала слоты, у Видаля оставалось одно фото, и модель
    рисовала второго Сиффреди плюс человека со съёмочной площадки.
    """
    inp = _inp(scene_refs=[f"s{i}" for i in range(8)])
    inp.actors = [
        ActorInput("Siffredi", "Rocco Siffredi", ["sf0", "sf1", "sf2", "sf3"]),
        ActorInput("Sins", "Johnny Sins, adult film actor", []),
        ActorInput("Vidal", "Nacho Vidal", ["vd0", "vd1", "vd2"]),
    ]
    prompt, refs = build(inp, max_refs=14)
    assert refs[:8] == ["p0", "sf0", "vd0", "sf1", "vd1", "sf2", "vd2", "sf3"]
    assert refs[8:] == ["s0", "s1", "s2", "s3", "s4", "s5"]
    assert "Each actor appears exactly once: Siffredi, Sins, Vidal." in prompt
    assert "Sins (Johnny Sins, adult film actor) has no reference photo." in prompt
    assert "Do not copy their face." in prompt
    assert "do not give two people the same face" in prompt
    assert "shows actor Sins" not in prompt


def test_content_filter_no_false_positives_on_common_words():
    assert content_filter.is_allowed("мяч не смог попасть в ворота, попадание было точным")
    assert content_filter.is_allowed("killer whale documentary")
    assert not content_filter.is_allowed("голая попа")
    assert not content_filter.is_allowed("kill him")
    assert content_filter.is_allowed("попкорн на диване")
    assert content_filter.is_allowed("грудинка свиная")
    assert content_filter.is_allowed("насилу успел на поезд")
    assert content_filter.is_allowed("театральная труппа")
    assert content_filter.is_allowed("трахея")
    assert content_filter.is_allowed("куница в лесу")
    assert content_filter.is_allowed("соскочить с поезда")
    assert content_filter.is_allowed("страх и класс")
    assert content_filter.is_allowed("мяч не смог попасть в ворота")
    assert content_filter.is_allowed("a cocktail at the bar")
    assert content_filter.is_allowed("reading Dickens")
    assert content_filter.is_allowed("on the grass near a zebra")
    assert content_filter.is_allowed("skill development")
    assert not content_filter.is_allowed("обнажённая грудь")
    assert not content_filter.is_allowed("без одежды")
    assert content_filter.is_allowed("sexy lingerie")
    assert content_filter.is_allowed("надень на неё белый купальник")
    assert content_filter.is_allowed("чёрное бикини")
    assert not content_filter.is_allowed("труп в комнате")
    assert not content_filter.is_allowed("nude on the bed")
    assert not content_filter.is_allowed("ГОЛЫЕ на пляже")
    assert content_filter.is_allowed("секстант на столе")
    assert content_filter.is_allowed("секстет исполнил вивальди")
    assert content_filter.is_allowed("стрингер крыла")
    assert content_filter.is_allowed("обнажение шейки зуба")
    assert content_filter.is_allowed("rapeseed oil")
    assert content_filter.is_allowed("gore-tex jacket")
    assert content_filter.is_allowed("the lawyer intimated")
    assert content_filter.is_allowed("booby prize")
    assert content_filter.is_allowed("pussycat on the windowsill")
    assert content_filter.is_allowed("bloodhound tracked the trail")
    assert content_filter.is_allowed("nudge him gently")
    assert content_filter.is_allowed("a portrait in the park")
    assert not content_filter.is_allowed("секс на пляже")
    assert not content_filter.is_allowed("обнажённая на диване")
    assert content_filter.is_allowed("в стрингах")
    assert not content_filter.is_allowed("фото ребёнка")
    assert not content_filter.is_allowed("a child on the beach")
    assert not content_filter.is_allowed("bloody murder")
    assert not content_filter.is_allowed("boobs out")


def test_content_filter_hyphenated_keywords_still_blocked():
    assert not content_filter.is_allowed("sex-photo on the beach")
    assert content_filter.is_allowed("sexy-pose by the pool")
    assert not content_filter.is_allowed("ass-shot from behind")
    assert not content_filter.is_allowed("boobs-out selfie")
    assert not content_filter.is_allowed("breast-shot close up")
    assert not content_filter.is_allowed("голый-парень на пляже")
    assert content_filter.is_allowed("стринги-фото")
    assert not content_filter.is_allowed("e-sex")
    assert content_filter.is_allowed("gore-tex jacket")
    assert content_filter.is_allowed("Gore-Tex boots")
    assert content_filter.is_allowed("well-dressed couple")
    assert content_filter.is_allowed("e-mail me")


def test_prompt_states_people_count():
    for people, actors, expected in [(1, 1, 2), (2, 1, 3), (1, 2, 3), (2, 2, 4)]:
        prompt, _ = build(_inp(people=people, actors=actors), max_refs=14)
        assert f"Exactly {expected} people in the frame, no other people in focus." in prompt


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
    prompt, refs = build(inp, max_refs=14)
    assert refs == ["p0"]
    assert "together with Actor0" in prompt
    assert "shows actor" not in prompt
    with pytest.raises(ValueError):
        build(_inp(people=2, actors=2), max_refs=3)


def test_build_edit_puts_previous_photo_first():
    prompt, refs = build_edit(_inp(people=2, actors=2, scene_ref="s"), "prev", "в пальто", max_refs=14)
    # предыдущий кадр первый; сцена и запасные ракурсы не подмешиваются
    assert refs == ["prev", "p0", "p1", "a0_0", "a1_0"]
    assert "shows the setting" not in prompt
    assert "Apply only this change, and apply it fully: в пальто." in prompt
    assert "Image 2 is person A." in prompt
    assert "Image 3 is person B." in prompt
    assert "Image 4 shows actor Actor0 (desc0)." in prompt
    assert "Image 5 shows actor Actor1 (desc1)." in prompt
    assert SAFETY_CLAUSE in prompt and REALISM_CLAUSE in prompt
    assert "same body build" in prompt


def test_build_edit_quality_request_does_not_redraw():
    prompt, refs = build_edit(_inp(scene_ref="s"), "prev", "Улучши качество изображения", max_refs=14)
    assert refs == ["prev"]
    assert "sharper" in prompt and "Do not redraw" in prompt
    assert "on a yacht" not in prompt


def test_build_edit_keeps_scene_text_out_of_the_prompt():
    prompt, _ = build_edit(_inp(), "prev", "даём пять", max_refs=14)
    assert "A candid photorealistic photo" not in prompt
    assert "on a yacht" not in prompt
    assert "Apply only this change, and apply it fully: даём пять." in prompt


def test_insert_sends_only_the_new_actor():
    """Видаль в кадр с Сиффреди: модели уходят только фото Видаля, не Сиффреди."""
    inp = GenerationInput(
        people=["wife"],
        actors=[
            ActorInput("Siffredi", "bald", ["siff-1", "siff-2", "siff-3", "siff-4"]),
            ActorInput("Sins", "", []),
            ActorInput("Vidal", "", ["vid-1", "vid-2", "vid-3"]),
        ],
        scene_prompt="in a modern office",
        scene_ref="office",
        detail=None,
        scene_refs=["office", "office-2"],
        width=832,
        height=1248,
        insert_target="actor",
        insert_actor_index=2,
    )
    prompt, refs = build_insert(inp, "prev", "Add Vidal into this exact photo.", max_refs=14)
    assert refs == ["prev", "vid-1", "vid-2", "vid-3"]
    assert "Siffredi" not in prompt and "Sins" not in prompt
    assert "Image 2 shows actor Vidal." in prompt
    assert "Image 3 also shows actor Vidal." in prompt
    assert "Add exactly one new person." in prompt
    assert "Do not duplicate anyone already in image 1" in prompt
    assert "is a location reference" not in prompt
    assert "in a modern office" not in prompt


def test_insert_named_actor_is_the_last_one_not_the_catalog():
    inp = _inp(actors=2)
    inp.actors.append(ActorInput("Vidal", "", ["vid-1"]))
    inp.insert_target = "named"
    inp.insert_actor_index = 2
    _prompt, refs = build_insert(inp, "prev", "Add Vidal.", max_refs=14)
    assert refs == ["prev", "vid-1"]


def test_insert_actor_without_photos_does_not_copy_faces_already_there():
    inp = _inp(actors=1)
    inp.actors.append(ActorInput("Sins", "", []))
    inp.insert_target = "actor"
    inp.insert_actor_index = 1
    prompt, refs = build_insert(inp, "prev", "Add Sins into this exact photo.", max_refs=14)
    assert refs == ["prev"]
    assert "The new person is Sins." in prompt
    assert "Do not copy a face already in image 1." in prompt
    assert "shows actor Actor0" not in prompt
    assert "p0" not in refs


def test_insert_self_sends_only_his_photo():
    inp = _inp(people=2, actors=2, scene_ref="s")
    inp.insert_target = "person"
    prompt, refs = build_insert(inp, "prev", "Add person B into this exact photo.", max_refs=14)
    assert refs == ["prev", "p1"]
    assert "Image 2 is person B." in prompt
    assert "shows actor" not in prompt
    assert "person A" not in prompt


def test_insert_keeps_the_new_face_when_refs_are_tight():
    inp = _inp()
    inp.actors[0].refs = ["a0_0", "a0_1", "a0_2", "a0_3"]
    inp.insert_target = "actor"
    inp.insert_actor_index = 0
    _prompt, refs = build_insert(inp, "prev", "Add Actor0.", max_refs=3)
    assert refs == ["prev", "a0_0", "a0_1"]


def test_insert_requires_a_target():
    with pytest.raises(ValueError):
        build_insert(_inp(), "prev", "Add someone.", max_refs=14)
    with pytest.raises(ValueError):
        build_insert(_inp(), "", "Add someone.", max_refs=14)


def test_build_edit_validates_inputs():
    with pytest.raises(ValueError):
        build_edit(_inp(), "", "в пальто", max_refs=14)
    with pytest.raises(ValueError):
        build_edit(_inp(), "prev", "   ", max_refs=14)
    with pytest.raises(ValueError):
        # один слот уходит под предыдущий кадр: людям и актёрам места не остаётся
        build_edit(_inp(people=2, actors=2), "prev", "в пальто", max_refs=4)
