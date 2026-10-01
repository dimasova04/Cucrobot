"""retire scenes that are not in the brief and rename the hotel door

Revision ID: f3a8c21b6e90
Revises: e6b1a9c44d28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a8c21b6e90"
down_revision: Union[str, Sequence[str], None] = "e6b1a9c44d28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RETIRED = (
    "Номер отеля, вечер",
    "На кастинге у Пьера",
    "Селфи после",
    "На кастинге у Пьера 2",
)
OLD_DOOR = "Отель, коридор"
NEW_DOOR = "Дверь номера"


def upgrade() -> None:
    conn = op.get_bind()
    for name in RETIRED:
        conn.execute(sa.text("UPDATE scenes SET is_active = false WHERE name = :name"), {"name": name})
    already = conn.execute(sa.text("SELECT id FROM scenes WHERE name = :name"), {"name": NEW_DOOR}).first()
    if already is None:
        conn.execute(
            sa.text("UPDATE scenes SET name = :new WHERE name = :old"),
            {"new": NEW_DOOR, "old": OLD_DOOR},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE scenes SET name = :old WHERE name = :new"),
        {"old": OLD_DOOR, "new": NEW_DOOR},
    )
    for name in RETIRED:
        conn.execute(sa.text("UPDATE scenes SET is_active = true WHERE name = :name"), {"name": name})
