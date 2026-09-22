"""Применение миграций Alembic при старте процесса.

Функция синхронная: внутри env.py вызывается asyncio.run(), поэтому вызывать её
из async-кода нужно через asyncio.to_thread.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parent.parent
INI_PATH = ROOT / "alembic.ini"


def make_config() -> Config:
    cfg = Config(str(INI_PATH))
    # Логирование уже настроено в main.py; fileConfig из alembic.ini снёс бы
    # перехват в loguru.
    cfg.attributes["configure_logger"] = False
    return cfg


def upgrade_to_head() -> None:
    command.upgrade(make_config(), "head")
