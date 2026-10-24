import asyncio
from email.message import EmailMessage
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import AnyHttpUrl, ValidationError

from identity.domain.value_objects.email import Email
from identity.infrastructure.config import MailSettings
from identity.infrastructure.email.smtp_email_sender import SmtpEmailSender


class FakeSmtp:
    def __init__(self) -> None:
        self.started_tls = False
        self.messages: list[EmailMessage] = []

    def __enter__(self) -> "FakeSmtp":  # noqa: PYI034
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        pass

    def starttls(self, *, context) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        raise AssertionError("SMTP login must not be called without credentials")

    def send_message(self, message: EmailMessage) -> None:
        self.messages.append(message)


def test_smtp_sender_sends_link_with_invitation_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smtp = FakeSmtp()
    monkeypatch.setattr(
        "identity.infrastructure.email.smtp_email_sender.smtplib.SMTP",
        lambda *args, **kwargs: smtp,
    )
    settings = MailSettings(
        smtp_host="smtp.example.com",
        smtp_from_email="identity@example.com",
        invitation_accept_url=AnyHttpUrl(
            "https://app.example.com/accept?source=email#password"
        ),
    )

    asyncio.run(SmtpEmailSender(settings).send(Email("person@example.com"), "a+b/="))

    assert smtp.started_tls
    assert len(smtp.messages) == 1
    message = smtp.messages[0]
    assert message["From"] == "identity@example.com"
    assert message["To"] == "person@example.com"
    body = message.get_content()
    assert isinstance(body, str)
    link = next(line for line in body.splitlines() if line.startswith("https://"))
    parts = urlsplit(link)
    assert parts.fragment == "password"
    assert parse_qs(parts.query) == {"source": ["email"], "token": ["a+b/="]}


def test_mail_settings_require_both_smtp_credentials() -> None:
    with pytest.raises(ValidationError):
        MailSettings(
            smtp_host="smtp.example.com",
            smtp_username="identity",
            smtp_from_email="identity@example.com",
            invitation_accept_url=AnyHttpUrl("https://app.example.com/accept"),
        )


def test_mail_settings_require_https_for_remote_invitation_urls() -> None:
    with pytest.raises(ValidationError):
        MailSettings(
            smtp_host="smtp.example.com",
            smtp_from_email="identity@example.com",
            invitation_accept_url=AnyHttpUrl("http://app.example.com/accept"),
        )
