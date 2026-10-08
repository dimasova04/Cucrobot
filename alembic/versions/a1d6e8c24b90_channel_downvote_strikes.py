"""10 downvotes remove a channel post and can ban posting

Revision ID: a1d6e8c24b90
Revises: f1b90c3e8d27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1d6e8c24b90"
down_revision: Union[str, Sequence[str], None] = "f1b90c3e8d27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("channel_ban_until", sa.DateTime(), nullable=True))
    op.create_index("ix_generations_channel_message_id", "generations", ["channel_message_id"])
    op.create_table(
        "channel_warnings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("generation_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["generations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generation_id", name="uq_channel_warning_generation"),
    )
    op.create_index("ix_channel_warnings_user_id", "channel_warnings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_warnings_user_id", table_name="channel_warnings")
    op.drop_table("channel_warnings")
    op.drop_index("ix_generations_channel_message_id", table_name="generations")
    op.drop_column("users", "channel_ban_until")
