import json
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Actor, ActorRef, Scene
from services.generation.local_assets import asset_file_id

SIZES = {"portrait": (832, 1248), "landscape": (1248, 832)}
MIN_REFS, MAX_REFS = 2, 4
# Пресс-волл AVN: модель переносит логотип в кадр. Эти файлы не отправляем.
PRESS_WALL_REFS = frozenset({
    "asset:actors/siffredi/01.jpg",
    "asset:actors/dupree/01.jpg",
    "asset:actors/dupree/02.jpg",
})
# У локации может быть больше кадров, чем у актёра: бюджет генерации всё равно 14.
SCENE_MAX_REFS = 8

# Раньше здесь был стоп-лист имён из порноиндустрии. Бот как раз ставит
# на фото актёра взрослого кино, поэтому имена больше не режем.
BLOCKED_ACTOR_NAMES: list[str] = []


def is_actor_name_allowed(name: str) -> bool:
    low = (name or "").lower()
    return not any(bad in low for bad in BLOCKED_ACTOR_NAMES)


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
        if active and len(actor.refs) < MIN_REFS:
            raise ValueError("actor has no reference photos")
        actor.is_active = active


async def add_actor_refs(session: AsyncSession, actor_id: int, file_ids: list[str]) -> Actor:
    actor = await session.get(Actor, actor_id)
    if actor is None:
        raise ValueError(f"actor {actor_id} not found")
    total = len(actor.refs) + len(file_ids)
    if total > MAX_REFS:
        raise ValueError(f"cannot exceed {MAX_REFS} reference photos, would have {total}")
    start = len(actor.refs)
    for i, fid in enumerate(file_ids):
        actor.refs.append(ActorRef(file_id=fid, is_primary=(start + i == 0), order=start + i))
    if len(actor.refs) >= MIN_REFS:
        actor.is_active = True
    await session.flush()
    return actor


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


def _bundled_ref_ids(item: dict, limit: int = MAX_REFS) -> list[str]:
    """Пути из yaml относительно assets/. Пустой список — кнопке хватает имени."""
    raw = item.get("refs") or []
    if not isinstance(raw, list):
        raise ValueError(f"refs for {item.get('name')} must be a list")
    if len(raw) > limit:
        raise ValueError(f"{item.get('name')} has {len(raw)} refs, max is {limit}")
    return [asset_file_id(str(rel)) for rel in raw]


def usable_ref_ids(file_ids: list[str]) -> list[str]:
    """Референсы актёра без пресс-волла. Логотип с того фото оказывается на готовом кадре."""
    return [fid for fid in file_ids if fid not in PRESS_WALL_REFS]


def _attach_refs(actor: Actor, file_ids: list[str]) -> None:
    for i, fid in enumerate(file_ids):
        actor.refs.append(ActorRef(file_id=fid, is_primary=(i == 0), order=i))


async def seed_actors(session: AsyncSession, path: str = "seed/actors.yaml") -> int:
    """Имена кнопок. Фото из yaml клеятся только если у актёра ещё нет референсов.

    Уже загруженные через бота file_id не затираются: следующий архив не сотрёт
    то, что админ поправил руками. Без фото актёр всё равно виден.
    """
    items = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    existing = {
        a.name: a for a in (await session.execute(select(Actor))).scalars().all()
    }
    order = await session.scalar(select(func.count()).select_from(Actor)) or 0
    added = 0
    for item in items:
        refs = _bundled_ref_ids(item)
        actor = existing.get(item["name"])
        if actor is None:
            actor = Actor(
                name=item["name"], description=(item.get("description") or "").strip(),
                is_active=True, order=order,
            )
            session.add(actor)
            if refs:
                _attach_refs(actor, refs)
            order += 1
            added += 1
            continue
        if refs and not actor.refs:
            _attach_refs(actor, refs)
    await session.flush()
    return added


def scene_ref_ids(scene) -> list[str]:
    """Кадры локации: список из ref_file_ids, иначе одно фото ref_file_id."""
    raw = getattr(scene, "ref_file_ids", None)
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list) and parsed:
            return [str(item) for item in parsed if item]
    if getattr(scene, "ref_file_id", None):
        return [scene.ref_file_id]
    return []


def _apply_scene_refs(scene: Scene, refs: list[str]) -> None:
    scene.ref_file_id = refs[0]
    scene.ref_file_ids = json.dumps(refs)


async def seed_scenes(session: AsyncSession, path: str = "seed/scenes.yaml") -> int:
    """Новые сцены из yaml. Кадры локации клеятся только если своих фото ещё нет."""
    items = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    existing = {s.name: s for s in (await session.execute(select(Scene))).scalars().all()}
    order = await session.scalar(select(func.count()).select_from(Scene)) or 0
    added = 0
    for item in items:
        refs = _bundled_ref_ids(item, SCENE_MAX_REFS)
        scene = existing.get(item["name"])
        if scene is None:
            scene = Scene(
                name=item["name"], prompt=item["prompt"], orientation=item["orientation"], order=order,
            )
            if refs:
                _apply_scene_refs(scene, refs)
            session.add(scene)
            order += 1
            added += 1
            continue
        if refs and not scene.ref_file_id and not scene.ref_file_ids:
            _apply_scene_refs(scene, refs)
    await session.flush()
    return added


# Обратная совместимость: раньше сидировал только пустую таблицу.
seed_scenes_if_empty = seed_scenes
