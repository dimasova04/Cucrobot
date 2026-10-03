"""location reference photos for the film set scene

Revision ID: e5c18a4d7b32
Revises: d8e3b71c4a90
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5c18a4d7b32"
down_revision: Union[str, Sequence[str], None] = "d8e3b71c4a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAME = "Съёмочная площадка"
REFS = [f"asset:scenes/set/{i:02d}.jpg" for i in range(1, 9)]
PROMPT = (
    "on a film set in a dressed room, studio lights on stands, a camera on a tripod, "
    "cables on the floor. Идёт съёмка, свет и камера в кадре."
)
PREVIOUS = "on a film set with cameras, lights and a clapperboard, behind-the-scenes photo, casual clothes"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE scenes SET prompt = :prompt, ref_file_id = :first, ref_file_ids = :ids "
            "WHERE name = :name"
        ),
        {"name": NAME, "prompt": PROMPT, "first": REFS[0], "ids": json.dumps(REFS)},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE scenes SET prompt = :prompt, ref_file_id = NULL, ref_file_ids = NULL "
            "WHERE name = :name"
        ),
        {"name": NAME, "prompt": PREVIOUS},
    )
