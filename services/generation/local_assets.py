"""Локальные референсы из репозитория. В базе лежат как `asset:actors/<slug>/01.jpg`."""

from pathlib import Path

ASSET_PREFIX = "asset:"
ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets"


def is_asset_ref(file_id: str) -> bool:
    return isinstance(file_id, str) and file_id.startswith(ASSET_PREFIX)


def resolve_asset(file_id: str) -> Path:
    """Путь к файлу внутри assets/. Выход за каталог и отсутствующий файл — ошибка."""
    if not is_asset_ref(file_id):
        raise ValueError("not an asset ref")
    rel = file_id[len(ASSET_PREFIX):].strip().lstrip("/")
    if not rel or "\\" in rel or rel.startswith("/"):
        raise ValueError("bad asset ref")
    root = ASSETS_ROOT.resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root):
        raise ValueError("bad asset ref")
    if not path.is_file():
        raise ValueError(f"asset ref not found: {rel}")
    return path


def asset_file_id(rel: str) -> str:
    """Проверяет, что файл есть, и возвращает id для колонки actor_refs.file_id."""
    rel = (rel or "").strip()
    if rel.startswith(ASSET_PREFIX):
        rel = rel[len(ASSET_PREFIX):]
    file_id = ASSET_PREFIX + rel.lstrip("/")
    resolve_asset(file_id)
    return file_id
