"""when an admin removes a channel post

Revision ID: c8f21a6e4b37
Revises: a7c3e91b4d20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8f21a6e4b37"
down_revision: Union[str, Sequence[str], None] = "a7c3e91b4d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("generations", sa.Column("channel_removed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("generations", "channel_removed_at")
