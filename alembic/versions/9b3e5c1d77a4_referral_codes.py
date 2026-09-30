"""referral codes and user attribution

Revision ID: 9b3e5c1d77a4
Revises: 7a1c2d3e4f50
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9b3e5c1d77a4"
down_revision: Union[str, Sequence[str], None] = "7a1c2d3e4f50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referral_codes",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=64), nullable=False),
        sa.Column("partner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("code"),
    )
    op.add_column("users", sa.Column("ref_code", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("ref_attributed_at", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_users_ref_code"), "users", ["ref_code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_ref_code"), table_name="users")
    op.drop_column("users", "ref_attributed_at")
    op.drop_column("users", "ref_code")
    op.drop_table("referral_codes")
