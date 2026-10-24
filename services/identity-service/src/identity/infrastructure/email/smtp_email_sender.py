import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from identity.domain.value_objects.email import Email
from identity.infrastructure.config import MailSettings


class SmtpEmailSender:
    def __init__(self, settings: MailSettings) -> None:
        self._settings = settings

    async def send(self, email: Email, plain_token: str) -> None:
        message = EmailMessage()
        message["From"] = self._settings.smtp_from_email
        message["To"] = email.value
        message["Subject"] = "Your FinGuard invitation"
        message.set_content(
            "You have been invited to FinGuard. Open this link to set your password:\n\n"
            f"{self._accept_link(plain_token)}\n"
        )
        await asyncio.to_thread(self._send_message, message)

    def _accept_link(self, plain_token: str) -> str:
        url = urlsplit(str(self._settings.invitation_accept_url))
        query = [
            (key, value)
            for key, value in parse_qsl(url.query, keep_blank_values=True)
            if key != "token"
        ]
        query.append(("token", plain_token))
        return urlunsplit(url._replace(query=urlencode(query)))

    def _send_message(self, message: EmailMessage) -> None:
        settings = self._settings
        timeout = settings.smtp_timeout_seconds
        if settings.smtp_security == "ssl":
            connection = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=timeout,
                context=ssl.create_default_context(),
            )
        else:
            connection = smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=timeout,
            )

        with connection as server:
            if settings.smtp_security == "starttls":
                server.starttls(context=ssl.create_default_context())
            if (
                settings.smtp_username is not None
                and settings.smtp_password is not None
            ):
                server.login(
                    settings.smtp_username,
                    settings.smtp_password.get_secret_value(),
                )
            server.send_message(message)
