"""align trade schema primary keys, indexes, constraints, and vtposition.created_dt not null

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-16

1. Backfill any NULL vtposition.created_dt with datetime and set NOT NULL
   (aligns legacy databases migrated via 95eb41d7a5ac with ORM vtPosition).
2. Add left-prefix indexes on experiment_id for vtorder, vtposition, and
   account to avoid sequential scans on per-experiment queries and ON DELETE
   CASCADE.
3. Promote standalone uq_vtorder_order_id unique index (if created by legacy
   f1a2b3c4d5e6) into a formal UNIQUE constraint so ORM metadata and pg_constraint
   stay consistent.
4. Align User (user_info) and Experiment (experiment) primary keys to single-column
   surrogate `id`:
   - `user_info`: replace composite PK `pd_id_user_client_id (id, user_id, client_id)`
     with `PRIMARY KEY (id)` + `UNIQUE (user_id, client_id)`.
   - `experiment`: replace legacy PK `pd_experiment_id (experiment_id)` with
     `PRIMARY KEY (id)` (`experiment_id` already has its own `UNIQUE` constraint).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Ensure vtposition.created_dt is NOT NULL
    op.execute("UPDATE vtposition SET created_dt = datetime WHERE created_dt IS NULL")
    op.alter_column(
        "vtposition",
        "created_dt",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    # 2. Ensure experiment_id foreign-key indexes exist
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vtorder_experiment_id ON vtorder (experiment_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vtposition_experiment_id ON vtposition (experiment_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_account_experiment_id ON account (experiment_id)"
    )

    # 3. Ensure uq_vtorder_order_id is registered in pg_constraint
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_vtorder_order_id'
                  AND conrelid = 'vtorder'::regclass
            ) THEN
                IF EXISTS (
                    SELECT 1
                    FROM pg_class c
                    JOIN pg_index i ON i.indexrelid = c.oid
                    WHERE c.relname = 'uq_vtorder_order_id'
                      AND i.indrelid = 'vtorder'::regclass
                      AND i.indisunique
                ) THEN
                    ALTER TABLE vtorder
                        ADD CONSTRAINT uq_vtorder_order_id
                        UNIQUE USING INDEX uq_vtorder_order_id;
                ELSE
                    ALTER TABLE vtorder
                        ADD CONSTRAINT uq_vtorder_order_id UNIQUE (order_id);
                END IF;
            END IF;
        END$$;
        """
    )

    # 4. Align user_info PK to (id) and add UNIQUE (user_id, client_id)
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE user_info DROP CONSTRAINT IF EXISTS pd_id_user_client_id;
            ALTER TABLE user_info DROP CONSTRAINT IF EXISTS user_info_pkey;
            ALTER TABLE user_info ADD CONSTRAINT user_info_pkey PRIMARY KEY (id);
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_user_id_client_id'
                  AND conrelid = 'user_info'::regclass
            ) THEN
                ALTER TABLE user_info
                    ADD CONSTRAINT uq_user_id_client_id UNIQUE (user_id, client_id);
            END IF;
        END$$;
        """
    )

    # 5. Align experiment PK to (id) while keeping experiment_id unique for FKs
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'experiment_experiment_id_key'
                  AND conrelid = 'experiment'::regclass
            ) THEN
                ALTER TABLE experiment
                    ADD CONSTRAINT experiment_experiment_id_key UNIQUE (experiment_id);
            END IF;
            ALTER TABLE experiment DROP CONSTRAINT IF EXISTS pd_experiment_id;
            ALTER TABLE experiment DROP CONSTRAINT IF EXISTS experiment_pkey;
            ALTER TABLE experiment ADD CONSTRAINT experiment_pkey PRIMARY KEY (id);
        END$$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE experiment DROP CONSTRAINT IF EXISTS experiment_pkey;
            ALTER TABLE experiment ADD CONSTRAINT pd_experiment_id PRIMARY KEY (id);
            ALTER TABLE user_info DROP CONSTRAINT IF EXISTS uq_user_id_client_id;
            ALTER TABLE user_info DROP CONSTRAINT IF EXISTS user_info_pkey;
            ALTER TABLE user_info
                ADD CONSTRAINT pd_id_user_client_id PRIMARY KEY (id, user_id, client_id);
        END$$;
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_account_experiment_id")
    op.execute("DROP INDEX IF EXISTS ix_vtposition_experiment_id")
    op.execute("DROP INDEX IF EXISTS ix_vtorder_experiment_id")
    op.alter_column(
        "vtposition",
        "created_dt",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
