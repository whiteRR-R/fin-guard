import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.infrastructure.config import DatabaseSettings, get_database_settings
from identity.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
)


MIGRATION_CONFIG = (
    Path(__file__).resolve().parents[3]
    / "src/identity/infrastructure/migration/migration.ini"
)


@pytest.fixture(autouse=True)
def database_settings_cache() -> Iterator[None]:
    get_database_settings.cache_clear()
    try:
        yield
    finally:
        get_database_settings.cache_clear()


def test_database_settings_factory_caches_until_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:secret@localhost/identity")
    settings = get_database_settings()

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:secret@localhost/another")

    assert get_database_settings() is settings
    assert settings.database_url.get_secret_value() == (
        "postgresql+asyncpg://user:secret@localhost/identity"
    )

    get_database_settings.cache_clear()
    reloaded_settings = get_database_settings()

    assert reloaded_settings is not settings
    assert reloaded_settings.database_url.get_secret_value() == (
        "postgresql+asyncpg://user:secret@localhost/another"
    )


def test_database_settings_read_url_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:secret@localhost/identity")

    settings = DatabaseSettings()

    assert settings.database_url.get_secret_value() == (
        "postgresql+asyncpg://user:secret@localhost/identity"
    )
    assert "secret" not in repr(settings)
    assert "secret" not in str(settings.model_dump())


def test_database_settings_require_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError, match="Field required"):
        DatabaseSettings(_env_file=None)


def test_database_settings_read_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        "DATABASE_URL=postgresql+asyncpg://user:secret@localhost/identity\n"
    )

    settings = DatabaseSettings(_env_file=dotenv_file)

    assert settings.database_url.get_secret_value() == (
        "postgresql+asyncpg://user:secret@localhost/identity"
    )


def test_database_engine_rejects_malformed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "invalid-url")
    settings = DatabaseSettings()

    with pytest.raises(ArgumentError):
        create_database_engine(settings)


def test_database_engine_and_session_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:secret@localhost/identity")
    engine = create_database_engine(DatabaseSettings())
    session_factory = create_session_factory(engine)
    session = session_factory()

    try:
        assert engine.url.drivername == "postgresql+asyncpg"
        assert engine.url.database == "identity"
        assert engine.url.password == "secret"
        assert session.bind is engine
        assert isinstance(session, AsyncSession)
        assert session.sync_session.expire_on_commit is False
    finally:
        asyncio.run(session.close())
        asyncio.run(engine.dispose())


def test_alembic_upgrade_and_downgrade_with_shared_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config(str(MIGRATION_CONFIG))
    engine = create_engine("sqlite://")

    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection

            command.upgrade(config, "head")
            assert MigrationContext.configure(connection).get_current_revision() == "b7c84a19d5e2"

            command.downgrade(config, "base")
            assert MigrationContext.configure(connection).get_current_revision() is None
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("database_url", "password"),
    [
        ("postgresql+asyncpg://user:secret@localhost/identity", "secret"),
        (
            "postgresql+asyncpg://user:secret%25value%40host@localhost/identity",
            "secret%value@host",
        ),
    ],
)
def test_alembic_generates_postgresql_sql(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    database_url: str,
    password: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(MIGRATION_CONFIG))

    command.upgrade(config, "head", sql=True)

    output = capsys.readouterr().out
    assert "CREATE TABLE alembic_version" in output
    assert "b7c84a19d5e2" in output
    assert "secret" not in output
    configured_url = config.get_main_option("sqlalchemy.url")
    assert configured_url is not None
    assert make_url(configured_url).password == password
