"""drop seeded actors that never got photos

Revision ID: 7a1c2d3e4f50
Revises: 842531f04cd6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7a1c2d3e4f50"
down_revision: Union[str, Sequence[str], None] = "842531f04cd6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Засеянные актёры имеют created_by IS NULL; удаляем только тех, кому так и не добавили фото.
    op.execute(
        sa.text(
            "DELETE FROM actors WHERE created_by IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM actor_refs WHERE actor_refs.actor_id = actors.id)"
        )
    )


def downgrade() -> None:
    pass  # данные не восстанавливаются
