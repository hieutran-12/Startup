import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

# Test truyền sẵn connection (tests/conftest.py): không cấu hình lại logging của pytest
shared_connection: Connection | None = config.attributes.get("connection")

if config.config_file_name is not None and shared_connection is None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# So cả kiểu cột và DEFAULT để autogenerate phát hiện model lệch migration
COMPARE_OPTIONS = {"compare_type": True, "compare_server_default": True}


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **COMPARE_OPTIONS,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, **COMPARE_OPTIONS)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif shared_connection is not None:
    do_run_migrations(shared_connection)
else:
    asyncio.run(run_async_migrations())
