"""set yacht, night club and office staging prompts

Revision ID: a91c4e7b2d05
Revises: f3a8c21b6e90
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a91c4e7b2d05"
down_revision: Union[str, Sequence[str], None] = "f3a8c21b6e90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROMPTS = {
    "Яхта": (
        "on the deck of a luxury yacht at sea, sunny day. Она в темном бикини",
        "on the deck of a luxury yacht at sea, sunny day, summer clothes, relaxed poses",
    ),
    "Ночной клуб": (
        "in a night club with neon lights and a crowd behind. "
        "Она в платье гоу-гоу, он одет в клубном стиле, держит ее за руку и смотрит на неё. "
        "Их видно в полный рост.",
        "in a night club with neon lights and a crowd behind, party outfits, laughing",
    ),
    "Офис": (
        "in a modern office. "
        "Он в деловом костюме, сидит у стола. "
        "Она секретарша одета только в мини и белую блузку, опирается руками на стол. "
        "Смотрят друг на друга",
        "in a modern office, standing by a glass wall, business attire, friendly conversation",
    ),
}


def upgrade() -> None:
    conn = op.get_bind()
    for name, (prompt, _previous) in PROMPTS.items():
        conn.execute(
            sa.text("UPDATE scenes SET prompt = :prompt WHERE name = :name"),
            {"name": name, "prompt": prompt},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for name, (_prompt, previous) in PROMPTS.items():
        conn.execute(
            sa.text("UPDATE scenes SET prompt = :prompt WHERE name = :name"),
            {"name": name, "prompt": previous},
        )
