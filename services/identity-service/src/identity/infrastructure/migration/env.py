import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from identity.infrastructure.config import DatabaseSettings
from identity.infrastructure.persistence.base import Base


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = DatabaseSettings()
    context.configure(
        url=settings.sqlalchemy_url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    settings = DatabaseSettings()
    engine = create_async_engine(settings.sqlalchemy_url, poolclass=pool.NullPool)

    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    connection = context.config.attributes.get("connection")
    if connection is None:
        asyncio.run(run_async_migrations())
    else:
        run_migrations(connection)
