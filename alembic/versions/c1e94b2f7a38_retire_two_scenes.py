"""deactivate retired scenes: red carpet and cafe

Revision ID: c1e94b2f7a38
Revises: b5f27ac31d90
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1e94b2f7a38"
down_revision: Union[str, Sequence[str], None] = "b5f27ac31d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RETIRED = ("Красная дорожка", "Кафе")


def upgrade() -> None:
    # Сцены убраны из seed/scenes.yaml; выключаем те, что уже успели засеяться.
    op.execute(
        sa.text("UPDATE scenes SET is_active = false WHERE name IN (:a, :b)").bindparams(
            a=RETIRED[0], b=RETIRED[1]
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE scenes SET is_active = true WHERE name IN (:a, :b)").bindparams(
            a=RETIRED[0], b=RETIRED[1]
        )
    )
