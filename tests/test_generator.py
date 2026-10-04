import asyncio
import base64
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from config.settings import Settings
from database import repo
from database.base import utcnow
from database.models import Generation
from services import catalog
from services.generation import faces
from services.generation.generator import (
    AlreadyRunning, GenerationRequest, Generator, TelegramFileFetcher, fail_stale_generations,
)
from services.generation.runware_client import ImageResult, RunwareGenerationError
from services.billing import wallet


def _settings():
    return Settings(_env_file=None, bot_token="x")


class FakeProvider:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def generate(self, model, prompt, refs, width, height, seed=None):
        self.calls.append({
            "model": model, "prompt": prompt, "refs": refs,
            "width": width, "height": height, "seed": seed,
        })
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeFetcher:
    async def fetch(self, file_id):
        return b"\xff\xd8" + file_id.encode()


async def _seed(factory, crystals=5):
    async with factory() as s:
        await repo.get_or_create_user(s, 1, "u")
        u = await repo.get_user(s, 1)
        u.crystals = crystals
        a = await catalog.create_actor(s, "Stat", "bald", ["fa1", "fa2"], 1)
        await catalog.seed_scenes_if_empty(s)
        scenes = await catalog.list_scenes(s)
        await s.commit()
        # вертикальная сцена: на ней проверяем размер кадра
        return a.id, next(sc for sc in scenes if sc.orientation == "portrait").id


def _req(actor_id, scene_id, tier="base", detail=None, **kw):
    return GenerationRequest(
        user_id=1, people_file_ids=["fp1"], actor_ids=[actor_id], scene_id=scene_id,
        custom_scene_text=None, custom_scene_file_id=None, detail=detail, tier=tier, **kw
    )


async def test_fetcher_reads_bundled_body_ref_and_rejects_escape():
    data = await TelegramFileFetcher(None).fetch("asset:actors/vidal/01.jpg")
    assert data[:2] == b"\xff\xd8" and len(data) > 1000
    fetcher = TelegramFileFetcher(None)
    with pytest.raises(ValueError):
        await fetcher.fetch("asset:../../.env")
    with pytest.raises(ValueError):
        await fetcher.fetch("asset:actors/vidal/../../../.env")


def test_location_faces_are_blanked_and_the_room_stays():
    import cv2
    import numpy as np
    from pathlib import Path

    raw = Path("assets/scenes/morning/05.jpg").read_bytes()
    blanked = faces.anonymize_faces(raw)
    assert blanked[:2] == b"\xff\xd8" and blanked != raw
    original = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    result = cv2.imdecode(np.frombuffer(blanked, dtype=np.uint8), cv2.IMREAD_COLOR)
    delta = np.abs(original.astype(np.int16) - result.astype(np.int16))
    # Лица пары в верхней половине. Угол подушки справа внизу не трогаем.
    assert delta[: original.shape[0] // 2].mean() > 4
    assert delta[-80:, -80:].mean() < 1
    assert faces.anonymize_faces(b"not an image") == b"not an image"


def test_film_set_crew_is_blanked_and_the_empty_room_stays():
    """Оператор на площадке смотрит вниз: детектор лиц его не видит, фигура остаётся."""
    import cv2
    import numpy as np
    from pathlib import Path

    raw = Path("assets/scenes/set/04.jpg").read_bytes()
    blanked = faces.anonymize_faces(raw)
    original = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    result = cv2.imdecode(np.frombuffer(blanked, dtype=np.uint8), cv2.IMREAD_COLOR)
    delta = np.abs(original.astype(np.int16) - result.astype(np.int16))
    # Оператор стоит слева. Правый край тумбы не трогаем.
    assert delta[180:530, 20:190].mean() > 8
    assert delta[:, -40:].mean() < 1

    empty = Path("assets/scenes/set/01.jpg").read_bytes()
    assert faces.anonymize_faces(empty) == empty


async def test_face_detector_returns_false_on_blank():
    import cv2, numpy as np
    blank = cv2.imencode(".jpg", np.zeros((300, 300, 3), dtype=np.uint8))[1].tobytes()
    assert faces.has_face(blank) is False
    assert faces.has_face(b"not an image") is False
    assert faces.detector_available() is True


async def test_face_detector_fails_open_when_cascade_unavailable(monkeypatch):
    import cv2, numpy as np
    blank = cv2.imencode(".jpg", np.zeros((300, 300, 3), dtype=np.uint8))[1].tobytes()
    monkeypatch.setattr(faces, "_CASCADE", None)
    monkeypatch.setattr(faces, "_cascade_load_attempted", True)
    assert faces.has_face(blank) is True


async def test_success_charges_and_records(session_factory, monkeypatch):
    actor_id, scene_id = await _seed(session_factory)
    provider = FakeProvider([ImageResult(url="http://x/img.jpg", cost=0.002, nsfw=False)])

    async def fake_download(url):
        return b"IMG"
    from services.generation import generator as g
    monkeypatch.setattr(g, "download_bytes", fake_download)

    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    out = await gen.run(_req(actor_id, scene_id))
    assert out.status == "done" and out.image_bytes == b"IMG" and out.cost_usd == 0.002
    call = provider.calls[0]
    assert call["model"] == "bytedance:seedream@4.5"
    assert len(call["refs"]) == 3 and all(r.startswith("data:image/jpeg;base64,") for r in call["refs"])
    assert (call["width"], call["height"]) == (1664, 2496)  # Seedream 4.5, вертикальная сцена
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 4
        row = await s.get(Generation, out.generation_id)
        assert row.status == "done" and row.crystals_charged == 1 and row.actors[0]["name"] == "Stat"
        assert row.result_url == "http://x/img.jpg"


async def test_named_actor_photo_replaces_catalog_actor(session_factory, monkeypatch):
    await _seed(session_factory)
    provider = FakeProvider([ImageResult(url="http://x/img.jpg", cost=0.002, nsfw=False)])
    from services.generation import generator as g

    async def fake_download(url):
        return b"IMG"

    monkeypatch.setattr(g, "download_bytes", fake_download)
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    req = GenerationRequest(
        user_id=1, people_file_ids=["fp1"], actor_ids=[], scene_id=None,
        custom_scene_text="on mars", custom_scene_file_id=None, detail=None,
        tier="base", named_actors=[("Рокко", ["hero1"])],
    )
    out = await gen.run(req)
    assert out.status == "done"
    call = provider.calls[0]
    # ровно два референса: фото пользователя и фото названного актёра
    assert len(call["refs"]) == 2
    assert "Exactly 2 people in the frame" in call["prompt"]
    assert "Рокко" in call["prompt"]
    async with session_factory() as s:
        row = await s.get(Generation, out.generation_id)
        assert row.actors == [{"id": None, "name": "Рокко"}]
        assert row.result_url == "http://x/img.jpg"


async def test_request_without_actor_or_hero_raises_before_charge(session_factory):
    await _seed(session_factory)
    provider = FakeProvider([])
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    req = GenerationRequest(
        user_id=1, people_file_ids=["fp1"], actor_ids=[], scene_id=None,
        custom_scene_text="on mars", custom_scene_file_id=None, detail=None, tier="base",
    )
    with pytest.raises(ValueError):
        await gen.run(req)
    assert provider.calls == []
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 5
        assert (await s.execute(select(func.count()).select_from(Generation))).scalar_one() == 0


async def test_failure_after_retry_refunds(session_factory):
    actor_id, scene_id = await _seed(session_factory)
    provider = FakeProvider([RunwareGenerationError("boom"), RunwareGenerationError("boom2")])
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    out = await gen.run(_req(actor_id, scene_id))
    assert out.status == "failed" and "boom2" in out.error
    assert len(provider.calls) == 2
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 5


async def test_nsfw_flag_still_delivers_the_image(session_factory, monkeypatch):
    actor_id, scene_id = await _seed(session_factory)
    provider = FakeProvider([ImageResult(url="http://x", cost=0.01, nsfw=True)])
    from services.generation import generator as g

    async def fake_download(url):
        return b"IMG"

    monkeypatch.setattr(g, "download_bytes", fake_download)
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    out = await gen.run(_req(actor_id, scene_id))
    assert out.status == "done" and out.image_bytes == b"IMG"
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 4


async def test_insufficient_balance_raises_before_generation(session_factory):
    actor_id, scene_id = await _seed(session_factory, crystals=0)
    provider = FakeProvider([])
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    with pytest.raises(wallet.InsufficientCrystals):
        await gen.run(_req(actor_id, scene_id))
    assert provider.calls == []


async def test_unknown_actor_id_raises_before_charge(session_factory):
    actor_id, scene_id = await _seed(session_factory)
    provider = FakeProvider([])
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    with pytest.raises(ValueError):
        await gen.run(_req(999999, scene_id))
    assert provider.calls == []
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 5
        assert (await s.execute(select(func.count()).select_from(Generation))).scalar_one() == 0


async def test_premium_uses_premium_model_and_cost(session_factory, monkeypatch):
    actor_id, scene_id = await _seed(session_factory)
    provider = FakeProvider([ImageResult(url="http://x", cost=0.05, nsfw=False)])
    from services.generation import generator as g
    async def fake_download(url):
        return b"IMG"
    monkeypatch.setattr(g, "download_bytes", fake_download)
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    out = await gen.run(_req(actor_id, scene_id, tier="premium"))
    assert out.status == "done" and provider.calls[0]["model"] == "google:4@3"
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 2


async def test_already_running_guard(session_factory):
    actor_id, scene_id = await _seed(session_factory)

    class Slow:
        async def generate(self, *a, **k):
            await asyncio.sleep(0.2)
            return ImageResult(url="http://x", cost=0, nsfw=True)

    gen = Generator(session_factory, Slow(), FakeFetcher(), _settings())
    t = asyncio.create_task(gen.run(_req(actor_id, scene_id)))
    await asyncio.sleep(0.05)
    with pytest.raises(AlreadyRunning):
        await gen.run(_req(actor_id, scene_id))
    await t


async def test_fail_stale_generations(session_factory):
    await _seed(session_factory)
    async with session_factory() as s:
        g = Generation(user_id=1, model_air="m", model_tier="base", actors=[], location="x", crystals_charged=1)
        s.add(g)
        await s.flush()
        await wallet.charge_generation(s, 1, 1, g.id)
        g.started_at = utcnow() - timedelta(minutes=10)
        await s.commit()
    assert await fail_stale_generations(session_factory, 5) == 1
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 5
        assert (await s.get(Generation, g.id)).status == "failed"


async def test_inactive_actor_raises_before_charge(session_factory):
    actor_id, scene_id = await _seed(session_factory)
    async with session_factory() as s:
        await catalog.set_actor_active(s, actor_id, False)
        await s.commit()
    provider = FakeProvider([])
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    with pytest.raises(ValueError):
        await gen.run(_req(actor_id, scene_id))
    assert provider.calls == []
    async with session_factory() as s:
        assert await wallet.get_balance(s, 1) == 5
        assert (await s.execute(select(func.count()).select_from(Generation))).scalar_one() == 0


async def test_detail_edit_reuses_previous_image_and_seed(session_factory, monkeypatch):
    """«Своя деталь» — правка поверх готового кадра: предыдущее фото идёт
    первым референсом, сид тот же."""
    actor_id, scene_id = await _seed(session_factory)
    provider = FakeProvider([
        ImageResult(url="http://x/first.jpg", cost=0.002, nsfw=False, seed=4242),
        ImageResult(url="http://x/second.jpg", cost=0.002, nsfw=False, seed=4242),
    ])
    from services.generation import generator as g

    async def fake_download(url):
        return b"PREV" if url == "http://x/first.jpg" else b"IMG"

    monkeypatch.setattr(g, "download_bytes", fake_download)
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())

    first = await gen.run(_req(actor_id, scene_id))
    assert first.status == "done" and first.seed == 4242
    assert provider.calls[0]["seed"] is None  # обычная генерация — без сида
    async with session_factory() as s:
        assert (await s.get(Generation, first.generation_id)).seed == 4242

    second = await gen.run(_req(
        actor_id, scene_id, detail="в пальто",
        edit_mode=True, base_generation_id=first.generation_id,
    ))
    assert second.status == "done"
    call = provider.calls[1]
    assert call["seed"] == 4242
    assert call["refs"][0] == "data:image/jpeg;base64," + base64.b64encode(b"PREV").decode()
    assert call["prompt"].startswith("Image 1 is the finished photo.")
    assert "Apply only this change, and apply it fully: в пальто." in call["prompt"]
    assert "do not add objects that were not requested" in call["prompt"]
    # ссылки на людей и актёра нумеруются со второй картинки
    assert "Image 2 is person A." in call["prompt"]
    async with session_factory() as s:
        row = await s.get(Generation, second.generation_id)
        assert row.status == "done" and row.crystals_charged == 1 and row.user_detail == "в пальто"


def _ref_payloads(refs: list[str]) -> list[bytes]:
    return [base64.b64decode(ref.split(",", 1)[1]) for ref in refs]


async def test_insert_actor_attaches_only_the_new_face(session_factory, monkeypatch):
    """В кадре уже Сиффреди и названный Рокко. Добавляем Видаля — его фото последние
    среди каталожных, но не последние вообще. Модели уходят только они."""
    actor_id, scene_id = await _seed(session_factory)
    async with session_factory() as s:
        vidal = await catalog.create_actor(s, "Видаль", "", ["vb1", "vb2", "vb3"], 1)
        await s.commit()
        vidal_id = vidal.id
    provider = FakeProvider([
        ImageResult(url="http://x/first.jpg", cost=0.002, nsfw=False, seed=7),
        ImageResult(url="http://x/second.jpg", cost=0.002, nsfw=False, seed=7),
    ])
    from services.generation import generator as g

    async def fake_download(url):
        return b"PREV" if url == "http://x/first.jpg" else b"IMG"

    monkeypatch.setattr(g, "download_bytes", fake_download)
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    first = await gen.run(_req(actor_id, scene_id))
    assert first.status == "done"

    second = await gen.run(GenerationRequest(
        user_id=1,
        people_file_ids=["wife"],
        actor_ids=[actor_id, vidal_id],
        named_actors=[("Рокко", ["rk1", "rk2"])],
        scene_id=scene_id,
        custom_scene_text=None,
        custom_scene_file_id=None,
        detail=None,
        tier="base",
        insert_prompt="Add Видаль into this exact photo.",
        insert_target="actor",
        edit_mode=True,
        base_generation_id=first.generation_id,
    ))
    assert second.status == "done"
    call = provider.calls[1]
    payloads = _ref_payloads(call["refs"])
    assert payloads[0] == b"PREV"
    assert payloads[1:] == [b"\xff\xd8" + name.encode() for name in ("vb1", "vb2", "vb3")]
    assert "Image 2 shows actor Видаль." in call["prompt"]
    assert "Stat" not in call["prompt"] and "Рокко" not in call["prompt"]
    assert "Add exactly one new person." in call["prompt"]
    async with session_factory() as s:
        row = await s.get(Generation, second.generation_id)
        assert [a["name"] for a in row.actors] == ["Stat", "Видаль", "Рокко"]


async def test_detail_edit_falls_back_when_base_download_fails(session_factory, monkeypatch):
    actor_id, scene_id = await _seed(session_factory)
    provider = FakeProvider([ImageResult(url="http://x/fresh.jpg", cost=0.002, nsfw=False, seed=7)])
    from services.generation import generator as g

    async def fake_download(url):
        if url == "http://x/gone.jpg":
            raise RuntimeError("link expired")
        return b"IMG"

    monkeypatch.setattr(g, "download_bytes", fake_download)
    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    async with session_factory() as s:
        base = Generation(
            user_id=1, model_air="m", model_tier="base", actors=[], location="x",
            crystals_charged=1, status="done", result_url="http://x/gone.jpg", seed=4242,
        )
        s.add(base)
        await s.commit()
        base_id = base.id

    out = await gen.run(_req(
        actor_id, scene_id, detail="в пальто", edit_mode=True, base_generation_id=base_id,
    ))
    assert out.status == "done"
    call = provider.calls[0]
    assert call["seed"] is None  # откат к обычной генерации
    assert call["prompt"].startswith("A candid photorealistic photo of")
    assert len(call["refs"]) == 3


async def test_detail_edit_ignores_foreign_or_unfinished_base(session_factory, monkeypatch):
    actor_id, scene_id = await _seed(session_factory)
    provider = FakeProvider([ImageResult(url="http://x/img.jpg", cost=0.002, nsfw=False, seed=7)])
    from services.generation import generator as g

    async def fake_download(url):
        return b"IMG"

    monkeypatch.setattr(g, "download_bytes", fake_download)
    async with session_factory() as s:
        await repo.get_or_create_user(s, 2, "other")
        foreign = Generation(
            user_id=2, model_air="m", model_tier="base", actors=[], location="x",
            crystals_charged=1, status="done", result_url="http://x/foreign.jpg", seed=1,
        )
        s.add(foreign)
        await s.commit()
        foreign_id = foreign.id

    gen = Generator(session_factory, provider, FakeFetcher(), _settings())
    out = await gen.run(_req(
        actor_id, scene_id, detail="в пальто", edit_mode=True, base_generation_id=foreign_id,
    ))
    assert out.status == "done"
    assert provider.calls[0]["seed"] is None
    assert provider.calls[0]["prompt"].startswith("A candid photorealistic photo of")
