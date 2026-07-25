import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.meta import MetaData

from alembic import context

# Import the ORM models so their table definitions register on the Base.metadata
# of each module. We keep both asset and trade metadata to support autogenerate.
# NOTE: imported lazily inside try/except so that alembic commands still work
# before the project dependencies (e.g. msgspec) are installed.
try:
    from bt_protocol.schema import asset as _asset_models  # noqa: F401
    from bt_protocol.schema import trade as _trade_models  # noqa: F401

    # Merge both DeclarativeBase.metadata into one target for autogenerate.
    target_metadata = MetaData()
    for _mod in (_asset_models, _trade_models):
        for _tbl in _mod.Base.metadata.tables.values():
            _tbl.tometadata(target_metadata)
except Exception:  # pragma: no cover - fallback if models cannot be imported
    target_metadata = None

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Allow the database URL to be injected via the DATABASE_URL env var so that
# credentials are not hardcoded in alembic.ini. Falls back to the ini value.
_db_url = os.getenv("DATABASE_URL")
if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
