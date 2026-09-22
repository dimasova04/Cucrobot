import sqlite3

from alembic import command

from config.settings import get_settings
from database.migrate import make_config

TABLES = {
    "users", "crystal_transactions", "generations", "payments",
    "actors", "actor_refs", "scenes",
}


def test_migrations_create_full_schema(tmp_path, monkeypatch):
    """env.py внутри вызывает asyncio.run(), поэтому тест синхронный."""
    db = tmp_path / "m.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    get_settings.cache_clear()
    try:
        command.upgrade(make_config(), "head")
    finally:
        get_settings.cache_clear()

    con = sqlite3.connect(db)
    try:
        names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        assert TABLES <= names
        assert "alembic_version" in names
        unique_cols = [
            [c[2] for c in con.execute(f"pragma index_info({idx[1]!r})")]
            for idx in con.execute("pragma index_list(payments)")
            if idx[2]
        ]
        assert ["provider", "external_id"] in unique_cols
    finally:
        con.close()
