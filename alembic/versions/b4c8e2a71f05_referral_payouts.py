"""referral payout requests

Revision ID: b4c8e2a71f05
Revises: a1d6e8c24b90
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4c8e2a71f05"
down_revision: Union[str, Sequence[str], None] = "a1d6e8c24b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referral_payouts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_kop", sa.Integer(), nullable=False),
        sa.Column("tg_username", sa.String(length=32), nullable=False),
        sa.Column("wallet", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_referral_payouts_user_id", "referral_payouts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_referral_payouts_user_id", table_name="referral_payouts")
    op.drop_table("referral_payouts")
