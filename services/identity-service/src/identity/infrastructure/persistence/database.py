from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from identity.infrastructure.config import DatabaseSettings


def create_database_engine(settings: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(settings.sqlalchemy_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
