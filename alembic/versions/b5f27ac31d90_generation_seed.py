"""generation seed for additive detail edits

Revision ID: b5f27ac31d90
Revises: 4d81a6c05e37
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5f27ac31d90"
down_revision: Union[str, Sequence[str], None] = "4d81a6c05e37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("generations", sa.Column("seed", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("generations", "seed")
