import argparse
import asyncio
import getpass
import sys
import warnings
from collections.abc import Sequence
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from identity.application.commands.bootstrap_first_admin.command import (
    BootstrapFirstAdminCommand,
)
from identity.application.commands.bootstrap_first_admin.handler import (
    BootstrapFirstAdminHandler,
)
from identity.application.exceptions import ApplicationException
from identity.domain.exceptions import DomainException
from identity.infrastructure.clock import SystemClock
from identity.infrastructure.config import get_database_settings
from identity.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
)
from identity.infrastructure.persistence.repositories.bootstrap_repository import (
    BootstrapRepository,
)
from identity.infrastructure.persistence.repositories.employee_repository import (
    EmployeeRepository,
)
from identity.infrastructure.persistence.repositories.outbox_repository import (
    OutboxRepository,
)
from identity.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from identity.infrastructure.security.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m identity.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create_admin = commands.add_parser(
        "create-admin", help="Create the first administrator"
    )
    create_admin.add_argument("--email", help="Administrator email address")
    return parser


async def _create_admin(email: str, password: str) -> UUID:
    engine = create_database_engine(get_database_settings())
    try:
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            handler = BootstrapFirstAdminHandler(
                uow=SqlAlchemyUnitOfWork(session),
                clock=SystemClock(),
                employees=EmployeeRepository(session),
                bootstrap=BootstrapRepository(session),
                password_hasher=BcryptPasswordHasher(),
                outbox=OutboxRepository(session),
            )
            result = await handler.execute(
                BootstrapFirstAdminCommand(email=email, password=password)
            )
            return result.employee_id
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        email = arguments.email or input("Administrator email: ")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("Password: ")
            confirmation = getpass.getpass("Confirm password: ")

        if password != confirmation:
            print("Passwords do not match", file=sys.stderr)
            return 2

        employee_id = asyncio.run(_create_admin(email, password))
    except (EOFError, KeyboardInterrupt):
        print("\nAdministrator creation cancelled", file=sys.stderr)
        return 2
    except getpass.GetPassWarning:
        print("A terminal with hidden password input is required", file=sys.stderr)
        return 2
    except ValidationError:
        print("Invalid database configuration: set DATABASE_URL", file=sys.stderr)
        return 2
    except (ApplicationException, DomainException) as error:
        print(f"Administrator creation failed: {error}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Administrator creation failed: database error", file=sys.stderr)
        return 1

    print(f"Administrator created: {employee_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
