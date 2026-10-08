"""drop actor photos that print an AVN logo into the frame

Revision ID: f1b90c3e8d27
Revises: e4c82b1d9a36
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1b90c3e8d27"
down_revision: Union[str, Sequence[str], None] = "e4c82b1d9a36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DROP = (
    "asset:actors/siffredi/01.jpg",
    "asset:actors/dupree/01.jpg",
    "asset:actors/dupree/02.jpg",
)


def _restore_primary(conn) -> None:
    actors = conn.execute(sa.text("SELECT DISTINCT actor_id FROM actor_refs")).fetchall()
    for (actor_id,) in actors:
        has_primary = conn.execute(
            sa.text("SELECT id FROM actor_refs WHERE actor_id = :id AND is_primary = :flag"),
            {"id": actor_id, "flag": True},
        ).first()
        if has_primary:
            continue
        first = conn.execute(
            sa.text('SELECT id FROM actor_refs WHERE actor_id = :id ORDER BY "order", id'),
            {"id": actor_id},
        ).first()
        if first:
            conn.execute(
                sa.text("UPDATE actor_refs SET is_primary = :flag WHERE id = :id"),
                {"id": first[0], "flag": True},
            )


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM actor_refs WHERE file_id = :a OR file_id = :b OR file_id = :c"),
        {"a": DROP[0], "b": DROP[1], "c": DROP[2]},
    )
    _restore_primary(conn)


def downgrade() -> None:
    conn = op.get_bind()
    restore = {
        "Сиффреди": ["asset:actors/siffredi/01.jpg"],
        "Дюпри": ["asset:actors/dupree/01.jpg", "asset:actors/dupree/02.jpg"],
    }
    for name, file_ids in restore.items():
        actor = conn.execute(
            sa.text("SELECT id FROM actors WHERE name = :name"), {"name": name}
        ).first()
        if actor is None:
            continue
        existing = {
            row[0]
            for row in conn.execute(
                sa.text("SELECT file_id FROM actor_refs WHERE actor_id = :id"),
                {"id": actor[0]},
            )
        }
        order = conn.execute(
            sa.text('SELECT COALESCE(MAX("order"), -1) FROM actor_refs WHERE actor_id = :id'),
            {"id": actor[0]},
        ).scalar()
        for fid in file_ids:
            if fid in existing:
                continue
            order += 1
            conn.execute(
                sa.text(
                    'INSERT INTO actor_refs (actor_id, file_id, is_primary, "order") '
                    "VALUES (:actor_id, :file_id, :flag, :ord)"
                ),
                {"actor_id": actor[0], "file_id": fid, "flag": False, "ord": order},
            )
