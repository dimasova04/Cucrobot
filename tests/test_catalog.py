import pytest

from database.models import Actor
from services import catalog
from services.generation.content_filter import is_allowed


async def test_seed_scenes_once(session_factory):
    async with session_factory() as s:
        assert await catalog.seed_scenes(s) == 12
        await s.commit()
    async with session_factory() as s:
        assert await catalog.seed_scenes(s) == 0
        scenes = await catalog.list_scenes(s)
        assert len(scenes) == 12
        names = [sc.name for sc in scenes]
        assert "Кухня, готовим вместе" not in names and "Париж, Эйфелева башня" not in names
        assert "На кастинге у Пьера" not in names and "За 1000 евро" in names
        assert "Утро после" in names and "Велкам-студия" in names and "На кастинге" in names
        assert "Гримёрка" not in names and "Лифт отеля" not in names and "Его кухня" not in names
        hotel = next(sc for sc in scenes if sc.name == "Дверь номера")
        assert "Она держит руками ручку двери и улыбается" in hotel.prompt
        assert "на нее и держит ее за талию" in hotel.prompt
        assert "holding key cards" not in hotel.prompt
        by_name = {sc.name: sc.prompt for sc in scenes}
        assert by_name["Яхта"].endswith("Она в темном бикини. Она улыбается")
        assert "summer clothes" not in by_name["Яхта"]
        assert "Она в платье гоу-гоу, он одет в клубном стиле, держит ее за руку и смотрит на неё. Их видно в полный рост. Она улыбается." in by_name["Ночной клуб"]
        assert "party outfits" not in by_name["Ночной клуб"]
        assert "Он в деловом костюме, сидит у стола. Она секретарша, улыбается. Она  одета только в черное мини и белую блузку, опирается руками на стол. Смотрят друг на друга" in by_name["Офис"]
        assert "business attire" not in by_name["Офис"]
        assert "Он одет только в гавайские шорты. Она в черном нижнем белье. Он смотрит на неё, она улыбается. Стоят у кровати" in by_name["Съёмочная площадка"]
        assert "clapperboard" not in by_name["Съёмочная площадка"]
        film = next(sc for sc in scenes if sc.name == "Съёмочная площадка")
        assert catalog.scene_ref_ids(film) == [f"asset:scenes/set/{i:02d}.jpg" for i in range(1, 9)]
        assert film.orientation == "landscape"
        mascara_prompt = by_name["Селфи с размазанной тушью"]
        assert "Она в черном нижнем белье и смеётся." in mascara_prompt
        assert "широкими чёрными потёками по обеим щекам" in mascara_prompt
        assert "не две маленькие точки" in mascara_prompt
        assert "looking at the phone" not in mascara_prompt
        mascara = next(sc for sc in scenes if sc.name == "Селфи с размазанной тушью")
        assert mascara.orientation == "portrait"
        assert catalog.scene_ref_ids(mascara) == [f"asset:scenes/mascara/{i:02d}.jpg" for i in range(1, 4)]
        assert "вытянув ноги вдоль сиденья ему на колени" in by_name["Лимузин"]
        assert "его рука лежит на ее лодыжке" in by_name["Лимузин"]
        assert "holding glasses" not in by_name["Лимузин"]
        euro_prompt = by_name["За 1000 евро"]
        assert euro_prompt.startswith("[solo] ")
        assert "Она одна в кадре и смотрит в камеру, на фотографа." in euro_prompt
        assert "Из переднего плана протянута рука с купюрами евро" in euro_prompt
        assert "это не человек в кадре" in euro_prompt
        assert "Она в черной кожаной куртке и черном бюстгалтере. Она улыбается." in euro_prompt
        assert "не накачанные" in euro_prompt
        assert "No other person stands in the frame." in euro_prompt
        assert "Do not add a man from the location photos" in euro_prompt
        assert "выбранный актёр" not in euro_prompt
        assert "casting room" not in euro_prompt
        limo = next(sc for sc in scenes if sc.name == "Лимузин")
        euro = next(sc for sc in scenes if sc.name == "За 1000 евро")
        assert catalog.scene_ref_ids(limo) == [
            "asset:scenes/limousine/01.jpg",
            "asset:scenes/limousine/02.jpg",
            "asset:scenes/limousine/03.jpg",
        ]
        assert catalog.scene_ref_ids(euro)[0] == "asset:scenes/euro/01.jpg"
        assert len(catalog.scene_ref_ids(euro)) == 4
        assert euro.orientation == "landscape"
        morning = next(sc for sc in scenes if sc.name == "Утро после")
        assert "a morning-after selfie with a white bathrobe" in morning.prompt
        assert "Белый халат на плечах" in morning.prompt
        assert "лёгкими следами" in morning.prompt
        assert "a close phone selfie" not in morning.prompt
        assert morning.prompt != by_name["Селфи с размазанной тушью"]
        assert "oversized shirt" not in morning.prompt
        assert morning.orientation == "portrait"
        assert "Одна комната" in morning.prompt
        assert "без софитов" in morning.prompt
        assert catalog.scene_ref_ids(morning) == [
            "asset:scenes/morning/02.jpg",
            "asset:scenes/morning/05.jpg",
        ]
        assert all(sc.orientation in catalog.SIZES for sc in scenes)
        assert all(sc.name and sc.prompt for sc in scenes)
        assert all(is_allowed(sc.prompt) for sc in scenes)


async def test_seed_scenes_adds_missing_only(session_factory):
    async with session_factory() as s:
        s.add(catalog.Scene(name="Яхта", prompt="placeholder", orientation="landscape"))
        await s.commit()
    async with session_factory() as s:
        assert await catalog.seed_scenes(s) == 11


async def test_seed_scenes_fills_empty_refs_and_keeps_uploaded(session_factory):
    async with session_factory() as s:
        s.add(catalog.Scene(
            name="Лимузин", prompt="keep", orientation="landscape", ref_file_id="tg-limo",
        ))
        s.add(catalog.Scene(name="Утро после", prompt="old", orientation="landscape"))
        await s.commit()
    async with session_factory() as s:
        await catalog.seed_scenes(s)
        await s.commit()
    async with session_factory() as s:
        scenes = {sc.name: sc for sc in await catalog.list_scenes(s, active_only=False)}
        assert scenes["Лимузин"].ref_file_id == "tg-limo"
        assert scenes["Лимузин"].ref_file_ids is None
        assert scenes["Лимузин"].prompt == "keep"
        assert scenes["Утро после"].prompt == "old"
        assert catalog.scene_ref_ids(scenes["Утро после"]) == [
            "asset:scenes/morning/02.jpg",
            "asset:scenes/morning/05.jpg",
        ]


async def _photoless_actor(session):
    a = Actor(name="Без фото", description="desc", is_active=False)
    session.add(a)
    await session.flush()
    return a


async def test_seed_actors_by_name(session_factory):
    async with session_factory() as s:
        assert await catalog.seed_actors(s) == 15
        await s.commit()
    async with session_factory() as s:
        assert await catalog.seed_actors(s) == 0
        actors = await catalog.list_actors(s)
        assert [a.name for a in actors][:3] == ["Сиффреди", "Синс", "Видаль"]
        siffredi = actors[0]
        assert siffredi.is_active
        assert [r.file_id for r in siffredi.refs] == [
            "asset:actors/siffredi/02.jpg",
            "asset:actors/siffredi/03.jpg",
            "asset:actors/siffredi/04.jpg",
        ]
        assert siffredi.refs[0].is_primary and not siffredi.refs[1].is_primary
        by_name = {a.name: a for a in actors}
        assert by_name["Синс"].refs == []
        assert len(by_name["Видаль"].refs) == 3
        assert len(by_name["Дюпри"].refs) == 1
        assert by_name["Дюпри"].refs[0].file_id == "asset:actors/dupree/03.jpg"
        assert by_name["Видаль"].refs[0].file_id == "asset:actors/vidal/01.jpg"
        assert "Джорди" in by_name and "Мик Блю" in by_name
    async with session_factory() as s:
        assert await catalog.seed_actors(s) == 0
        actors = await catalog.list_actors(s)
        assert len(next(a for a in actors if a.name == "Сиффреди").refs) == 3


async def test_seed_actors_fills_empty_and_keeps_uploaded_refs(session_factory):
    from database.models import ActorRef

    async with session_factory() as s:
        uploaded = Actor(name="Сиффреди", description="keep", is_active=True, order=0)
        uploaded.refs = [ActorRef(file_id="tg-photo", is_primary=True, order=0)]
        s.add(uploaded)
        s.add(Actor(name="Видаль", description="empty", is_active=True, order=1))
        await s.commit()
    async with session_factory() as s:
        assert await catalog.seed_actors(s) == 13
        await s.commit()
    async with session_factory() as s:
        actors = {a.name: a for a in await catalog.list_actors(s, active_only=False)}
        assert [r.file_id for r in actors["Сиффреди"].refs] == ["tg-photo"]
        assert [r.file_id for r in actors["Видаль"].refs] == [
            "asset:actors/vidal/01.jpg",
            "asset:actors/vidal/02.jpg",
            "asset:actors/vidal/03.jpg",
        ]
        assert actors["Дюпри"].refs[0].file_id == "asset:actors/dupree/03.jpg"


def test_press_wall_photos_are_not_sent_to_the_model():
    assert catalog.usable_ref_ids([
        "asset:actors/siffredi/01.jpg",
        "asset:actors/siffredi/02.jpg",
        "asset:actors/dupree/01.jpg",
        "asset:actors/dupree/02.jpg",
        "asset:actors/dupree/03.jpg",
        "tg-photo",
    ]) == [
        "asset:actors/siffredi/02.jpg",
        "asset:actors/dupree/03.jpg",
        "tg-photo",
    ]


async def test_seed_actors_rejects_missing_or_too_many_refs(session_factory, tmp_path):
    missing = tmp_path / "missing.yaml"
    missing.write_text(
        '- name: "Тест"\n  description: "x"\n  refs:\n    - actors/no-such.jpg\n',
        encoding="utf-8",
    )
    async with session_factory() as s:
        with pytest.raises(ValueError):
            await catalog.seed_actors(s, path=str(missing))
    too_many = tmp_path / "many.yaml"
    too_many.write_text(
        '- name: "Тест"\n  description: "x"\n  refs:\n'
        "    - actors/siffredi/01.jpg\n    - actors/siffredi/02.jpg\n"
        "    - actors/siffredi/03.jpg\n    - actors/siffredi/04.jpg\n"
        "    - actors/vidal/01.jpg\n",
        encoding="utf-8",
    )
    async with session_factory() as s:
        with pytest.raises(ValueError):
            await catalog.seed_actors(s, path=str(too_many))


async def test_add_actor_refs_activates_and_caps(session_factory):
    async with session_factory() as s:
        aid = (await _photoless_actor(s)).id
        await s.commit()
    async with session_factory() as s:
        await catalog.add_actor_refs(s, aid, ["r1"])
        await s.commit()
    async with session_factory() as s:
        actor = await catalog.get_actor(s, aid)
        assert not actor.is_active
        assert actor.refs[0].is_primary
        await catalog.add_actor_refs(s, aid, ["r2"])
        await s.commit()
    async with session_factory() as s:
        actor = await catalog.get_actor(s, aid)
        assert actor.is_active
        assert len(actor.refs) == 2
        await catalog.add_actor_refs(s, aid, ["r3", "r4"])
        await s.commit()
    async with session_factory() as s:
        actor = await catalog.get_actor(s, aid)
        assert len(actor.refs) == 4
        with pytest.raises(ValueError):
            await catalog.add_actor_refs(s, aid, ["r5"])


async def test_set_actor_active_requires_refs(session_factory):
    async with session_factory() as s:
        aid = (await _photoless_actor(s)).id
        await s.commit()
    async with session_factory() as s:
        with pytest.raises(ValueError):
            await catalog.set_actor_active(s, aid, True)


async def test_actor_crud_and_ref_validation(session_factory):
    async with session_factory() as s:
        with pytest.raises(ValueError):
            await catalog.create_actor(s, "X", "desc", ["only_one"], 1)
        a = await catalog.create_actor(s, "Джейсон Стэйтем", "bald man, stubble", ["f1", "f2", "f3"], 1)
        await s.commit()
    async with session_factory() as s:
        actors = await catalog.list_actors(s)
        assert [x.name for x in actors] == ["Джейсон Стэйтем"]
        assert actors[0].refs[0].is_primary and len(actors[0].refs) == 3
        await catalog.set_actor_active(s, a.id, False)
        await s.commit()
    async with session_factory() as s:
        assert await catalog.list_actors(s) == []
        assert len(await catalog.list_actors(s, active_only=False)) == 1
        await catalog.delete_actor(s, a.id)
        await s.commit()
    async with session_factory() as s:
        assert await catalog.list_actors(s, active_only=False) == []


def test_actor_names_are_not_blocked():
    from services import catalog

    assert catalog.BLOCKED_ACTOR_NAMES == []
    for name in [
        "Том Харди", "Jason Statham", "Анджелина Джоли",
        "Джонни Синс", "Johnny Sins", "Пьер Вудман", "Pierre Woodman",
    ]:
        assert catalog.is_actor_name_allowed(name), name
