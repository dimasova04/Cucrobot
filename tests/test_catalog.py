import pytest

from database.models import Actor
from services import catalog
from services.generation.content_filter import is_allowed


async def test_seed_scenes_once(session_factory):
    async with session_factory() as s:
        assert await catalog.seed_scenes(s) == 20
        await s.commit()
    async with session_factory() as s:
        assert await catalog.seed_scenes(s) == 0
        scenes = await catalog.list_scenes(s)
        assert len(scenes) == 20
        assert all(sc.orientation in catalog.SIZES for sc in scenes)
        assert all(sc.name and sc.prompt for sc in scenes)
        assert all(is_allowed(sc.prompt) for sc in scenes)


async def test_seed_scenes_adds_missing_only(session_factory):
    async with session_factory() as s:
        s.add(catalog.Scene(name="Кафе", prompt="placeholder", orientation="landscape"))
        await s.commit()
    async with session_factory() as s:
        assert await catalog.seed_scenes(s) == 19


async def _photoless_actor(session):
    a = Actor(name="Без фото", description="desc", is_active=False)
    session.add(a)
    await session.flush()
    return a


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
