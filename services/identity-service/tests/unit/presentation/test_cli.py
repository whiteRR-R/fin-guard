import asyncio
import getpass
import warnings
from uuid import UUID, uuid4

from sqlalchemy.sql.elements import TextClause

from identity import cli
from identity.domain.enums.role import EmployeeRole
from identity.domain.enums.status import EmployeeStatus
from identity.infrastructure.persistence.models.employee import EmployeeModel
from identity.infrastructure.persistence.models.outbox_message import OutboxMessageModel


def test_create_admin_prompts_for_password_without_printing_it(
    monkeypatch, capsys
) -> None:
    employee_id = uuid4()
    received: list[tuple[str, str]] = []
    prompts: list[str] = []

    async def create_admin(email: str, password: str) -> UUID:
        received.append((email, password))
        return employee_id

    def read_password(prompt: str) -> str:
        prompts.append(prompt)
        return "very-secret-password"

    monkeypatch.setattr(cli, "_create_admin", create_admin)
    monkeypatch.setattr(cli.getpass, "getpass", read_password)

    assert cli.main(["create-admin", "--email", "admin@example.com"]) == 0

    output = capsys.readouterr()
    assert received == [("admin@example.com", "very-secret-password")]
    assert prompts == ["Password: ", "Confirm password: "]
    assert str(employee_id) in output.out
    assert "very-secret-password" not in output.out + output.err


def test_create_admin_rejects_mismatched_passwords_before_database_access(
    monkeypatch, capsys
) -> None:
    passwords = iter(("very-secret-password", "different-password"))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(passwords))

    def fail_if_called(*args, **kwargs) -> None:
        raise AssertionError("Database must not be accessed")

    monkeypatch.setattr(cli, "_create_admin", fail_if_called)

    assert cli.main(["create-admin", "--email", "admin@example.com"]) == 2
    assert "Passwords do not match" in capsys.readouterr().err


def test_create_admin_refuses_visible_password_fallback(monkeypatch, capsys) -> None:
    def unsafe_prompt(prompt: str) -> str:
        warnings.warn("Password input may be echoed", getpass.GetPassWarning)
        return "very-secret-password"

    monkeypatch.setattr(cli.getpass, "getpass", unsafe_prompt)

    assert cli.main(["create-admin", "--email", "admin@example.com"]) == 2
    assert "hidden password input is required" in capsys.readouterr().err


def test_create_admin_uses_one_session_for_employee_and_outbox(
    monkeypatch,
) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []
            self.commits = 0
            self.entries = 0

        async def __aenter__(self) -> "FakeSession":  # noqa: PYI034
            self.entries += 1
            return self

        async def __aexit__(self, exc_type, exc_value, traceback) -> None:
            pass

        async def scalar(self, statement) -> bool | None:
            return True if isinstance(statement, TextClause) else None

        def add(self, value: object) -> None:
            self.added.append(value)

        async def commit(self) -> None:
            self.commits += 1

        async def rollback(self) -> None:
            pass

    class FakeEngine:
        def __init__(self) -> None:
            self.disposals = 0

        async def dispose(self) -> None:
            self.disposals += 1

    session = FakeSession()
    engine = FakeEngine()
    monkeypatch.setattr(cli, "get_database_settings", lambda: object())
    monkeypatch.setattr(cli, "create_database_engine", lambda _: engine)
    monkeypatch.setattr(cli, "create_session_factory", lambda _: lambda: session)

    employee_id = asyncio.run(
        cli._create_admin("admin@example.com", "very-secret-password")
    )

    employees = [item for item in session.added if isinstance(item, EmployeeModel)]
    outbox = [item for item in session.added if isinstance(item, OutboxMessageModel)]
    assert len(employees) == len(outbox) == 1
    assert employees[0].id == employee_id
    assert employees[0].status is EmployeeStatus.ACTIVE
    assert employees[0].roles == [EmployeeRole.ADMIN]
    assert employees[0].password_hash is not None
    assert employees[0].password_hash.startswith("$2b$")
    assert outbox[0].message_type == "FirstAdminBootstrapped"
    assert session.entries == session.commits == engine.disposals == 1
