"""add merge / ratio in asset

Revision ID: 79a49578303d
Revises: 70e341d5e7a8
Create Date: 2026-06-15 14:43:42.518248

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79a49578303d'
down_revision: Union[str, Sequence[str], None] = '70e341d5e7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('asset', sa.Column('merger', sa.LargeBinary(), nullable=True))
    op.add_column('asset', sa.Column('ratio', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('asset', 'merger')
    op.drop_column('asset', 'ratio')
