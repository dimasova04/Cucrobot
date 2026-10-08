"""morning scene: one room, drop the collage refs

Revision ID: e4c82b1d9a36
Revises: c3a91e7b2d14
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4c82b1d9a36"
down_revision: Union[str, Sequence[str], None] = "c3a91e7b2d14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAME = "Утро после"
REFS = [
    "asset:scenes/morning/02.jpg",
    "asset:scenes/morning/05.jpg",
]
PREVIOUS_REFS = [f"asset:scenes/morning/{i:02d}.jpg" for i in range(1, 6)]
PROMPT = (
    "a morning-after selfie with a white bathrobe, not a tight crying close-up. "
    "Белый халат на плечах, под ним бельё, телефон в руке. Он рядом и прижимается к ней. "
    "Смотрят в камеру. Тушь только лёгкими следами, не широкими чёрными потёками по щекам. "
    "Одна комната, без софитов, камеры на штативе и бассейна. Кожа резкая, как на фото людей, не пластиковая."
)
PREVIOUS = (
    "a morning-after selfie with a white bathrobe, not a tight crying close-up. "
    "Белый халат на плечах, под ним бельё, телефон в руке. Он рядом и прижимается к ней. "
    "Смотрят в камеру. Тушь только лёгкими следами, не широкими чёрными потёками по щекам."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE scenes SET prompt = :prompt, ref_file_id = :first, ref_file_ids = :ids "
            "WHERE name = :name"
        ),
        {"name": NAME, "prompt": PROMPT, "first": REFS[0], "ids": json.dumps(REFS)},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE scenes SET prompt = :prompt, ref_file_id = :first, ref_file_ids = :ids "
            "WHERE name = :name"
        ),
        {
            "name": NAME,
            "prompt": PREVIOUS,
            "first": PREVIOUS_REFS[0],
            "ids": json.dumps(PREVIOUS_REFS),
        },
    )
