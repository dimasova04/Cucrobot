"""who invited the user

Revision ID: c3a91e7b2d14
Revises: b7e2c91a4f08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3a91e7b2d14"
down_revision: Union[str, Sequence[str], None] = "b7e2c91a4f08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("invited_by", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "invited_by")
