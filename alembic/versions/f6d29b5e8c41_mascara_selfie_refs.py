"""location reference photos for the smudged-mascara selfie

Revision ID: f6d29b5e8c41
Revises: e5c18a4d7b32
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6d29b5e8c41"
down_revision: Union[str, Sequence[str], None] = "e5c18a4d7b32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAME = "Селфи с размазанной тушью"
REFS = [f"asset:scenes/mascara/{i:02d}.jpg" for i in range(1, 4)]
PROMPT = (
    "a close phone selfie. У неё размазана тушь под глазами. "
    "Он вплотную рядом с ней. Смотрят в камеру."
)
PREVIOUS = (
    "a close phone selfie, her mascara is smudged under the eyes, "
    "he is beside her, both looking at the phone"
)


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
