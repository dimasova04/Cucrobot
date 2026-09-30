"""generation result url for HD download

Revision ID: 4d81a6c05e37
Revises: 9b3e5c1d77a4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4d81a6c05e37"
down_revision: Union[str, Sequence[str], None] = "9b3e5c1d77a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("generations", sa.Column("result_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("generations", "result_url")
