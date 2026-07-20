"""Email composition and SMTP delivery adapter."""

from __future__ import annotations

import smtplib
from collections.abc import Callable, Sequence
from email.message import EmailMessage

from ccip.config import SMTPConfig

SMTPFactory = Callable[..., smtplib.SMTP]


def compose_email(
    *, sender: str, recipients: Sequence[str], subject: str, html: str, text: str
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message


class SMTPDelivery:
    """Synchronous SMTP adapter implementing the EmailDelivery protocol."""

    def __init__(self, config: SMTPConfig, smtp_factory: SMTPFactory = smtplib.SMTP) -> None:
        self.config = config
        self.smtp_factory = smtp_factory

    def deliver(self, message: EmailMessage) -> None:
        with self.smtp_factory(
            self.config.host,
            self.config.port,
            timeout=self.config.timeout_seconds,
        ) as client:
            if self.config.start_tls:
                client.starttls()
            if self.config.username:
                password = self.config.password.get_secret_value() if self.config.password else ""
                client.login(self.config.username, password)
            client.send_message(message)

