"""retire unused scenes and set the hotel-corridor prompt

Revision ID: e6b1a9c44d28
Revises: c1e94b2f7a38
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6b1a9c44d28"
down_revision: Union[str, Sequence[str], None] = "c1e94b2f7a38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RETIRED = (
    "Селфи на улице",
    "Диван, вечер кино",
    "Ужин при свечах",
    "Париж, Эйфелева башня",
    "Пляж на закате",
    "Горнолыжный курорт",
    "Стадион",
    "За кулисами концерта",
    "Частный самолёт",
    "Кухня, готовим вместе",
    "Спорткар",
)

HOTEL_NAME = "Отель, коридор"
HOTEL_PROMPT = (
    "standing at a hotel room door in a hotel corridor. "
    "Она в черном открытом купальнике. Он смотрит на нее и держит ее за талию и локоть. "
    "Она держит руками ручку двери"
)
HOTEL_PROMPT_PREVIOUS = (
    "standing at a hotel room door in a hotel corridor, holding key cards, smiling at the camera, dressed"
)


def upgrade() -> None:
    conn = op.get_bind()
    for name in RETIRED:
        conn.execute(sa.text("UPDATE scenes SET is_active = false WHERE name = :name"), {"name": name})
    conn.execute(
        sa.text("UPDATE scenes SET prompt = :prompt WHERE name = :name"),
        {"name": HOTEL_NAME, "prompt": HOTEL_PROMPT},
    )


def downgrade() -> None:
    conn = op.get_bind()
    for name in RETIRED:
        conn.execute(sa.text("UPDATE scenes SET is_active = true WHERE name = :name"), {"name": name})
    conn.execute(
        sa.text("UPDATE scenes SET prompt = :prompt WHERE name = :name"),
        {"name": HOTEL_NAME, "prompt": HOTEL_PROMPT_PREVIOUS},
    )
