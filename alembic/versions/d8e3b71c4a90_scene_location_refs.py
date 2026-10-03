"""location reference photos for limousine, 1000 euro and morning after

Revision ID: d8e3b71c4a90
Revises: c4d8e1a90b27
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8e3b71c4a90"
down_revision: Union[str, Sequence[str], None] = "c4d8e1a90b27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LIMO = "Лимузин"
EURO = "За 1000 евро"
MORNING = "Утро после"

LIMO_REFS = [
    "asset:scenes/limousine/01.jpg",
    "asset:scenes/limousine/02.jpg",
    "asset:scenes/limousine/03.jpg",
]
EURO_REFS = [
    "asset:scenes/euro/01.jpg",
    "asset:scenes/euro/02.jpg",
    "asset:scenes/euro/03.jpg",
    "asset:scenes/euro/04.jpg",
]
MORNING_REFS = [
    "asset:scenes/morning/01.jpg",
    "asset:scenes/morning/02.jpg",
    "asset:scenes/morning/03.jpg",
    "asset:scenes/morning/04.jpg",
    "asset:scenes/morning/05.jpg",
]

EURO_PROMPT = (
    "outdoors in daylight, greenery behind. "
    "Из переднего плана протянута рука с купюрами евро. Она смотрит на деньги."
)
EURO_PREVIOUS = (
    "in a small casting room under a soft key light, she poses in a black swimsuit, "
    "he looks at her and holds her elbow"
)
MORNING_PROMPT = (
    "a close phone selfie in the morning. "
    "У неё размазана тушь, телефон в руке. Он рядом и прижимается к ней. Смотрят в камеру."
)
MORNING_PREVIOUS = (
    "in a sunlit bedroom in the morning, messy white sheets, she wears an oversized shirt, "
    "he sits on the edge of the bed"
)


def _set_refs(conn, name: str, refs: list[str]) -> None:
    conn.execute(
        sa.text(
            "UPDATE scenes SET ref_file_id = :first, ref_file_ids = :ids WHERE name = :name"
        ),
        {"name": name, "first": refs[0], "ids": json.dumps(refs)},
    )


def upgrade() -> None:
    op.add_column("scenes", sa.Column("ref_file_ids", sa.Text(), nullable=True))
    conn = op.get_bind()
    _set_refs(conn, LIMO, LIMO_REFS)
    conn.execute(
        sa.text(
            "UPDATE scenes SET prompt = :prompt, orientation = 'landscape' WHERE name = :name"
        ),
        {"name": EURO, "prompt": EURO_PROMPT},
    )
    _set_refs(conn, EURO, EURO_REFS)
    conn.execute(
        sa.text(
            "UPDATE scenes SET prompt = :prompt, orientation = 'portrait' WHERE name = :name"
        ),
        {"name": MORNING, "prompt": MORNING_PROMPT},
    )
    _set_refs(conn, MORNING, MORNING_REFS)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE scenes SET ref_file_id = NULL WHERE name IN (:limo, :euro, :morning)"),
        {"limo": LIMO, "euro": EURO, "morning": MORNING},
    )
    conn.execute(
        sa.text(
            "UPDATE scenes SET prompt = :prompt, orientation = 'portrait' WHERE name = :name"
        ),
        {"name": EURO, "prompt": EURO_PREVIOUS},
    )
    conn.execute(
        sa.text(
            "UPDATE scenes SET prompt = :prompt, orientation = 'landscape' WHERE name = :name"
        ),
        {"name": MORNING, "prompt": MORNING_PREVIOUS},
    )
    op.drop_column("scenes", "ref_file_ids")
