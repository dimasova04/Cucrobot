"""public name and channel post id

Revision ID: a7c3e91b4d20
Revises: b8e14c6a9d52
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e91b4d20"
down_revision: Union[str, Sequence[str], None] = "b8e14c6a9d52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite не умеет ADD CONSTRAINT, поэтому уникальность — через batch.
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("public_name", sa.String(length=32), nullable=True))
        batch.create_unique_constraint("uq_users_public_name", ["public_name"])
    op.add_column("generations", sa.Column("channel_message_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("generations", "channel_message_id")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_public_name", type_="unique")
        batch.drop_column("public_name")
