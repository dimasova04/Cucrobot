"""user preferred_tier

Revision ID: 842531f04cd6
Revises: c86fadefd4c4
Create Date: 2026-09-22 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '842531f04cd6'
down_revision: Union[str, Sequence[str], None] = 'c86fadefd4c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("preferred_tier", sa.String(16), nullable=False, server_default="base"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "preferred_tier")
