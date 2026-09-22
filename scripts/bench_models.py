"""Ручной стенд: одна и та же задача через несколько моделей Runware.

Пример:
  .venv/bin/python scripts/bench_models.py --person me.jpg \
    --actor "Stat:bald man with stubble:refs/stat1.jpg,refs/stat2.jpg" \
    --scene "on a yacht deck, sunny day" --orientation landscape

Актёр указывается как NAME:DESCRIPTION:PATH[,PATH,...].
Описание может содержать двоеточия; пути к файлам не должны содержать запятых.
"""
import argparse
import asyncio
import base64
import re
import time
from pathlib import Path

import httpx

from config.settings import get_settings
from services.catalog import SIZES
from services.generation.prompt_builder import ActorInput, GenerationInput, build
from services.generation.runware_client import RunwareClient


def _uri(path: str) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def _parse_actor(spec: str) -> ActorInput:
    parts = spec.split(":")
    if len(parts) < 3:
        raise SystemExit(f"bad --actor spec {spec!r}: expected NAME:DESC:PATH[,PATH]")
    name = parts[0]
    paths = parts[-1]
    desc = ":".join(parts[1:-1])
    return ActorInput(name, desc, [_uri(p) for p in paths.split(",")])


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--person", nargs="+", required=True)
    ap.add_argument("--actor", action="append", required=True)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--orientation", default="portrait", choices=list(SIZES))
    ap.add_argument("--models", default="runware:400@2,bytedance:seedream@4.5,google:4@3")
    ap.add_argument("--out", default="bench_out")
    args = ap.parse_args()

    settings = get_settings()
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    width, height = SIZES[args.orientation]
    inp = GenerationInput([_uri(p) for p in args.person], [_parse_actor(a) for a in args.actor], args.scene, None, None, width, height)
    client = RunwareClient(settings.runware_api_key, settings.gen_timeout_sec)
    print(f"{'model':32} {'cost':>8} {'sec':>6} nsfw")
    for model in args.models.split(","):
        max_refs = 4 if model.startswith("runware:400@") else 14
        t0 = time.perf_counter()
        try:
            prompt, refs = build(inp, max_refs)
            res = await client.generate(model, prompt, refs, width, height)
        except Exception as e:
            print(f"{model:32} FAILED {e}")
            continue
        sec = time.perf_counter() - t0
        async with httpx.AsyncClient(timeout=60) as c:
            data = (await c.get(res.url)).content
        slug = re.sub(r"[^a-z0-9]+", "_", model.lower())
        (out / f"{slug}.jpg").write_bytes(data)
        print(f"{model:32} {res.cost or 0:8.4f} {sec:6.1f} {res.nsfw}")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
