import pytest

from database.models import Actor
from services import catalog
from services.generation.content_filter import is_allowed


async def test_seed_scenes_once(session_factory):
    async with session_factory() as s:
        assert await catalog.seed_scenes(s) == 13
        await s.commit()
    async with session_factory() as s:
        assert await catalog.seed_scenes(s) == 0
        scenes = await catalog.list_scenes(s)
        assert len(scenes) == 13
        names = [sc.name for sc in scenes]
        assert "Кухня, готовим вместе" not in names and "Париж, Эйфелева башня" not in names
        assert "На кастинге у Пьера" not in names and "За 1000 евро" in names
        assert "Утро после" in names and "Гримёрка" in names and "Лифт отеля" in names and "Его кухня" in names
        hotel = next(sc for sc in scenes if sc.name == "Дверь номера")
        assert "Она в черном открытом купальнике." in hotel.prompt
        assert "holding key cards" not in hotel.prompt
        by_name = {sc.name: sc.prompt for sc in scenes}
        assert by_name["Яхта"].endswith("Она в темном бикини")
        assert "summer clothes" not in by_name["Яхта"]
        assert "Она в платье гоу-гоу, он одет в клубном стиле, держит ее за руку и смотрит на неё. Их видно в полный рост." in by_name["Ночной клуб"]
        assert "party outfits" not in by_name["Ночной клуб"]
        assert "Он в деловом костюме, сидит у стола. Она секретарша одета только в мини и белую блузку, опирается руками на стол. Смотрят друг на друга" in by_name["Офис"]
        assert "business attire" not in by_name["Офис"]
        assert "Идёт съёмка, свет и камера в кадре." in by_name["Съёмочная площадка"]
        assert "clapperboard" not in by_name["Съёмочная площадка"]
        film = next(sc for sc in scenes if sc.name == "Съёмочная площадка")
        assert catalog.scene_ref_ids(film) == [f"asset:scenes/set/{i:02d}.jpg" for i in range(1, 9)]
        assert film.orientation == "landscape"
        assert "вытянув ноги вдоль сиденья ему на колени" in by_name["Лимузин"]
        assert "его рука лежит на ее лодыжке" in by_name["Лимузин"]
        assert "holding glasses" not in by_name["Лимузин"]
        assert "Из переднего плана протянута рука с купюрами евро" in by_name["За 1000 евро"]
        assert "casting room" not in by_name["За 1000 евро"]
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
        assert "У неё размазана тушь, телефон в руке" in morning.prompt
        assert "oversized shirt" not in morning.prompt
        assert morning.orientation == "portrait"
        assert catalog.scene_ref_ids(morning) == [
            "asset:scenes/morning/01.jpg",
            "asset:scenes/morning/02.jpg",
            "asset:scenes/morning/03.jpg",
            "asset:scenes/morning/04.jpg",
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
        assert await catalog.seed_scenes(s) == 12


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
            "asset:scenes/morning/01.jpg",
            "asset:scenes/morning/02.jpg",
            "asset:scenes/morning/03.jpg",
            "asset:scenes/morning/04.jpg",
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
            "asset:actors/siffredi/01.jpg",
            "asset:actors/siffredi/02.jpg",
            "asset:actors/siffredi/03.jpg",
            "asset:actors/siffredi/04.jpg",
        ]
        assert siffredi.refs[0].is_primary and not siffredi.refs[1].is_primary
        by_name = {a.name: a for a in actors}
        assert by_name["Синс"].refs == []
        assert len(by_name["Видаль"].refs) == 3
        assert len(by_name["Дюпри"].refs) == 3
        assert by_name["Видаль"].refs[0].file_id == "asset:actors/vidal/01.jpg"
        assert "Джорди" in by_name and "Мик Блю" in by_name
    async with session_factory() as s:
        assert await catalog.seed_actors(s) == 0
        actors = await catalog.list_actors(s)
        assert len(next(a for a in actors if a.name == "Сиффреди").refs) == 4


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
        assert actors["Дюпри"].refs[0].file_id == "asset:actors/dupree/01.jpg"


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
