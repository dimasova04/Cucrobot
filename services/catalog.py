from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Actor, ActorRef, Scene

SIZES = {"portrait": (832, 1248), "landscape": (1248, 832)}
MIN_REFS, MAX_REFS = 2, 4


async def list_actors(session: AsyncSession, active_only: bool = True) -> list[Actor]:
    q = select(Actor).order_by(Actor.order, Actor.id)
    if active_only:
        q = q.where(Actor.is_active.is_(True))
    return list((await session.execute(q)).scalars().all())


async def get_actor(session: AsyncSession, actor_id: int) -> Actor | None:
    return await session.get(Actor, actor_id)


async def create_actor(
    session: AsyncSession, name: str, description: str, file_ids: list[str], created_by: int | None
) -> Actor:
    if not MIN_REFS <= len(file_ids) <= MAX_REFS:
        raise ValueError(f"need {MIN_REFS}-{MAX_REFS} reference photos, got {len(file_ids)}")
    actor = Actor(name=name.strip(), description=description.strip(), created_by=created_by)
    actor.refs = [
        ActorRef(file_id=fid, is_primary=(i == 0), order=i) for i, fid in enumerate(file_ids)
    ]
    session.add(actor)
    await session.flush()
    return actor


async def set_actor_active(session: AsyncSession, actor_id: int, active: bool) -> None:
    actor = await session.get(Actor, actor_id)
    if actor:
        actor.is_active = active


async def delete_actor(session: AsyncSession, actor_id: int) -> None:
    actor = await session.get(Actor, actor_id)
    if actor:
        await session.delete(actor)
        await session.flush()


async def list_scenes(session: AsyncSession, active_only: bool = True) -> list[Scene]:
    q = select(Scene).order_by(Scene.order, Scene.id)
    if active_only:
        q = q.where(Scene.is_active.is_(True))
    return list((await session.execute(q)).scalars().all())


async def get_scene(session: AsyncSession, scene_id: int) -> Scene | None:
    return await session.get(Scene, scene_id)


async def create_scene(
    session: AsyncSession, name: str, prompt: str, orientation: str, ref_file_id: str | None, created_by: int | None
) -> Scene:
    if orientation not in SIZES:
        raise ValueError(f"orientation must be one of {list(SIZES)}")
    scene = Scene(
        name=name.strip(), prompt=prompt.strip(), orientation=orientation,
        ref_file_id=ref_file_id, created_by=created_by,
    )
    session.add(scene)
    await session.flush()
    return scene


async def set_scene_active(session: AsyncSession, scene_id: int, active: bool) -> None:
    scene = await session.get(Scene, scene_id)
    if scene:
        scene.is_active = active


async def delete_scene(session: AsyncSession, scene_id: int) -> None:
    scene = await session.get(Scene, scene_id)
    if scene:
        await session.delete(scene)
        await session.flush()


async def seed_scenes_if_empty(session: AsyncSession, path: str = "seed/scenes.yaml") -> int:
    existing = await session.execute(select(Scene.id).limit(1))
    if existing.scalar_one_or_none() is not None:
        return 0
    items = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for i, item in enumerate(items):
        session.add(Scene(name=item["name"], prompt=item["prompt"], orientation=item["orientation"], order=i))
    await session.flush()
    return len(items)
