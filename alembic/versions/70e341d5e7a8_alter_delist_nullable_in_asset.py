"""alter delist nullable in asset

Revision ID: 70e341d5e7a8
Revises: 
Create Date: 2026-06-15 14:20:46.886014

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '70e341d5e7a8'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'asset',                     
        'delist',                    
        existing_type=sa.Integer(),   
        nullable=True
        # server_default=None      # 清除数据库层面的默认值               
    )


def downgrade() -> None:
    """Downgrade schema."""
    # ensure not null in pg
    op.alter_column(
        'asset',
        'delist',
        existing_type=sa.Integer(),
        nullable=False
        # server_default='0'
    )
