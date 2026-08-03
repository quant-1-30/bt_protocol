"""create trade tables (user_info, experiment, vtorder, order_bit, vtposition, account)

Revision ID: a0b1c2d3e4f5
Revises:
Create Date: 2026-08-03 15:50:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a0b1c2d3e4f5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_info',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=255, collation='C'), nullable=False),
        sa.Column('client_id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint('id', 'user_id', 'client_id', name='pd_id_user_client_id'),
        sa.UniqueConstraint('client_id', name='user_info_client_id_key'),
    )
    op.create_table(
        'experiment',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('client_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy', sa.Text(collation='C'), nullable=False),
        sa.Column('extra_info', sa.Text(collation='C'), nullable=False),
        sa.Column('experiment_id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['user_info.client_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pd_experiment_id'),
        sa.UniqueConstraint('client_id', 'strategy', 'extra_info', name='uq_client_strategy_extra_info'),
        sa.UniqueConstraint('experiment_id', name='experiment_experiment_id_key'),
    )
    op.create_table(
        'vtorder',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sid', sa.LargeBinary(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('size', sa.Integer(), server_default='0', nullable=False),
        sa.Column('order_type', sa.Integer(), nullable=False),
        sa.Column('exec_type', sa.Integer(), nullable=False),
        sa.Column('created_dt', sa.BigInteger(), nullable=False),
        sa.Column('order_id', sa.LargeBinary(), nullable=False),
        sa.Column('experiment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['experiment_id'], ['experiment.experiment_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sid', 'created_dt', 'experiment_id',
                            name='uq_order_sid_created_dt_experiment_id'),
    )
    op.create_unique_constraint('uq_vtorder_order_id', 'vtorder', ['order_id'])
    op.create_table(
        'order_bit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.LargeBinary(), nullable=False),
        sa.Column('executed_dt', sa.BigInteger(), nullable=False),
        sa.Column('executed_price', sa.Float(), nullable=False),
        sa.Column('executed_size', sa.Integer(), server_default='0', nullable=False),
        sa.Column('comm', sa.Float(), nullable=False),
        sa.Column('isbuy', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['vtorder.order_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_id', name='order_bit_order_id_key'),
        sa.UniqueConstraint('order_id', 'executed_dt', name='uq_order_executed_dt'),
    )
    op.create_table(
        'vtposition',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sid', sa.LargeBinary(), nullable=False),
        sa.Column('datetime', sa.BigInteger(), nullable=False),
        sa.Column('cost_basis', sa.Float(), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('available', sa.Integer(), nullable=False),
        sa.Column('pnl', sa.Float(), nullable=False),
        sa.Column('experiment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['experiment_id'], ['experiment.experiment_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('datetime', 'sid', 'experiment_id',
                            name='uq_position_datetime_sid_experiment_id'),
    )
    op.create_table(
        'account',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('datetime', sa.BigInteger(), nullable=False),
        sa.Column('portfolio_value', sa.Float(), nullable=False),
        sa.Column('cash', sa.Float(), nullable=False),
        sa.Column('pnl', sa.Float(), nullable=False),
        sa.Column('leverage', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('margin', sa.Float(), server_default='0', nullable=False),
        sa.Column('experiment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['experiment_id'], ['experiment.experiment_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('datetime', 'experiment_id', name='uq_acct_datetime_experiment_id'),
    )


def downgrade() -> None:
    op.drop_table('account')
    op.drop_table('vtposition')
    op.drop_table('order_bit')
    op.drop_table('vtorder')
    op.drop_table('experiment')
    op.drop_table('user_info')