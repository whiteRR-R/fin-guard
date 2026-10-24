import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from identity.infrastructure.clock import SystemClock
from identity.infrastructure.config import (
    MailSettings,
    TokenSettings,
    get_database_settings,
)
from identity.infrastructure.email.smtp_email_sender import SmtpEmailSender
from identity.infrastructure.outbox.invitation_email_worker import (
    InvitationEmailWorker,
)
from identity.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
)
from identity.infrastructure.security.hmac_invitation_tokens import (
    HmacInvitationTokens,
)

logger = logging.getLogger(__name__)


async def run_worker(*, once: bool, poll_interval: float) -> int:
    token_settings = TokenSettings()
    mail_settings = MailSettings()
    database_settings = get_database_settings()
    clock = SystemClock()
    tokens = HmacInvitationTokens(
        signing_key=token_settings.invitation_signing_key.get_secret_value().encode(
            "utf-8"
        ),
        lifetime=timedelta(days=token_settings.invitation_token_lifetime_days),
    )
    engine = create_database_engine(database_settings)
    try:
        worker = InvitationEmailWorker(
            session_factory=create_session_factory(engine),
            clock=clock,
            token_issuer=tokens,
            token_verifier=tokens,
            email_sender=SmtpEmailSender(mail_settings),
        )

        failures = 0
        while True:
            result = await worker.process_one()
            if result == "retry":
                failures += 1
            if result == "idle":
                if once:
                    return 1 if failures else 0
                await asyncio.sleep(poll_interval)
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m identity.outbox_worker")
    parser.add_argument(
        "--once", action="store_true", help="Process due invitations and exit"
    )
    parser.add_argument("--poll-interval", type=float, default=5.0)
    arguments = parser.parse_args(argv)
    if arguments.poll_interval <= 0:
        parser.error("--poll-interval must be positive")

    logging.basicConfig(level=logging.INFO)
    try:
        return asyncio.run(
            run_worker(once=arguments.once, poll_interval=arguments.poll_interval)
        )
    except KeyboardInterrupt:
        return 0
    except ValidationError:
        print("Invalid outbox worker configuration", file=sys.stderr)
        return 2
    except SQLAlchemyError as error:
        logger.error("Outbox worker database failure (%s)", type(error).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
