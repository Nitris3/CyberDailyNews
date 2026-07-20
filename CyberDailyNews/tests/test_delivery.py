from email.message import EmailMessage

from ccip.config import SMTPConfig
from ccip.delivery import SMTPDelivery, compose_email


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, *, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tls_started = False
        self.credentials: tuple[str, str] | None = None
        self.message: EmailMessage | None = None
        self.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def starttls(self) -> None:
        self.tls_started = True

    def login(self, username: str, password: str) -> None:
        self.credentials = (username, password)

    def send_message(self, message: EmailMessage) -> None:
        self.message = message


def test_compose_email_is_multipart_with_html_fallback() -> None:
    message = compose_email(
        sender="sender@example.com",
        recipients=["one@example.com", "two@example.com"],
        subject="Daily report",
        html="<h1>Report</h1>",
        text="Report",
    )

    assert message["To"] == "one@example.com, two@example.com"
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "Report"
    assert "<h1>Report</h1>" in message.get_body(preferencelist=("html",)).get_content()


def test_smtp_delivery_uses_tls_and_credentials() -> None:
    FakeSMTP.instances.clear()
    config = SMTPConfig(
        host="smtp.example.com",
        port=587,
        username="user",
        password="secret",
        start_tls=True,
    )
    message = EmailMessage()

    SMTPDelivery(config, smtp_factory=FakeSMTP).deliver(message)  # type: ignore[arg-type]

    client = FakeSMTP.instances[0]
    assert client.tls_started
    assert client.credentials == ("user", "secret")
    assert client.message is message

