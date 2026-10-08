import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession

from identity.infrastructure.config import DatabaseSettings
from identity.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
)


MIGRATION_CONFIG = (
    Path(__file__).resolve().parents[3]
    / "src/identity/infrastructure/migration/migration.ini"
)


def test_database_settings_read_url_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:secret@localhost/identity")

    settings = DatabaseSettings()

    assert settings.sqlalchemy_url.drivername == "postgresql+asyncpg"
    assert settings.sqlalchemy_url.database == "identity"
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

    assert settings.sqlalchemy_url.database == "identity"


@pytest.mark.parametrize(
    ("url", "error"),
    [
        ("invalid-url", "DATABASE_URL is invalid"),
        ("sqlite+aiosqlite:///identity.db", r"postgresql\+asyncpg driver"),
        ("postgresql+asyncpg://user:secret@localhost", "database name"),
    ],
)
def test_database_settings_reject_invalid_url(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    error: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", url)

    with pytest.raises(ValidationError, match=error) as exc_info:
        DatabaseSettings(_env_file=None)

    assert "secret" not in str(exc_info.value)


def test_database_engine_and_session_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:secret@localhost/identity")
    engine = create_database_engine(DatabaseSettings())
    session_factory = create_session_factory(engine)
    session = session_factory()

    try:
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

            command.check(config)

            command.downgrade(config, "base")
            assert MigrationContext.configure(connection).get_current_revision() is None
    finally:
        engine.dispose()


def test_alembic_generates_postgresql_sql(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:secret@localhost/identity")
    command.upgrade(Config(str(MIGRATION_CONFIG)), "head", sql=True)

    output = capsys.readouterr().out
    assert "CREATE TABLE alembic_version" in output
    assert "b7c84a19d5e2" in output
    assert "secret" not in output
