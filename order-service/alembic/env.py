import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.database import Base
from app import models  # noqa: F401 - ensures all models are registered on Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Both replicas of this service run `alembic upgrade head` on startup
# (see entrypoint.sh). Without serialization, two containers starting at the
# same time can both see "migration not applied yet" and race to run the
# same CREATE TYPE / CREATE TABLE statements, and the loser crashes with a
# "already exists" error. A Postgres advisory lock makes the second process
# simply wait, then find the migration already applied and no-op.
MIGRATION_LOCK_ID = 727271


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # The advisory lock lives on its own AUTOCOMMIT connection, entirely
    # separate from the connection Alembic uses to run migrations. Mixing
    # the two on one connection let Alembic's own `begin_transaction()`
    # swallow/interfere with the lock's transaction, which is why the first
    # version of this fix did not actually prevent the race. Two independent
    # connections means the lock is genuinely held for the whole migration.
    lock_engine = connectable.execution_options(isolation_level="AUTOCOMMIT")
    async with lock_engine.connect() as lock_connection:
        # Blocks here until any concurrently-starting replica finishes its
        # own migration run, instead of racing it.
        await lock_connection.execute(
            text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID}
        )
        try:
            async with connectable.connect() as connection:
                await connection.run_sync(do_run_migrations)
        finally:
            await lock_connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID}
            )

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
