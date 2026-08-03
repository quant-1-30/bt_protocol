"""add unique constraint on vtorder.order_id

Revision ID: f1a2b3c4d5e6
Revises: 95eb41d7a5ac
Create Date: 2026-08-03 12:56:00.000000

Idempotent: the table-creation root a0b1c2d3e4f5 may already have created
this index on fresh databases.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "95eb41d7a5ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_vtorder_order_id ON vtorder (order_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_vtorder_order_id")
