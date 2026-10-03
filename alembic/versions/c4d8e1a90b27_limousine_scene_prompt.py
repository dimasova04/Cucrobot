"""set the limousine staging prompt

Revision ID: c4d8e1a90b27
Revises: a91c4e7b2d05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d8e1a90b27"
down_revision: Union[str, Sequence[str], None] = "a91c4e7b2d05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAME = "Лимузин"
PROMPT = (
    "inside a black limousine at night, city lights through the side windows, black leather seat, "
    "champagne glasses on the side console. "
    "Она в коротком черном платье и черных босоножках, сидит, вытянув ноги вдоль сиденья ему на колени. "
    "Он в темном костюме и белой рубашке без галстука, его рука лежит на ее лодыжке. "
    "Смотрят друг на друга."
)
PREVIOUS = "inside a limousine with city lights through the window, evening wear, holding glasses of champagne"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE scenes SET prompt = :prompt WHERE name = :name"),
        {"name": NAME, "prompt": PROMPT},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE scenes SET prompt = :prompt WHERE name = :name"),
        {"name": NAME, "prompt": PREVIOUS},
    )
