import pytest

from ccip.cli import build_parser, smtp_config_for_delivery
from ccip.config import SMTPConfig


def test_cli_parses_database_initialization() -> None:
    arguments = build_parser().parse_args(["--config", "custom.yml", "init-db"])

    assert arguments.config == "custom.yml"
    assert arguments.command == "init-db"


def test_cli_parses_collection_command() -> None:
    arguments = build_parser().parse_args(["collect"])

    assert arguments.command == "collect"


def test_cli_parses_preview_date_and_output() -> None:
    arguments = build_parser().parse_args(
        ["preview", "--date", "2026-07-20", "--output", "report.html", "--open"]
    )

    assert arguments.date.isoformat() == "2026-07-20"
    assert arguments.output == "report.html"
    assert arguments.open is True


def test_cli_preview_does_not_open_browser_by_default() -> None:
    arguments = build_parser().parse_args(["preview"])

    assert arguments.open is False
    assert arguments.resummarize is False


def test_cli_preview_ai_rewrite_is_explicit() -> None:
    arguments = build_parser().parse_args(["preview", "--resummarize"])

    assert arguments.resummarize is True


def test_cli_send_is_dry_run_by_default() -> None:
    arguments = build_parser().parse_args(["send", "--date", "2026-07-20"])

    assert arguments.command == "send"
    assert arguments.confirm_send is False
    assert arguments.dry_run is False


def test_cli_send_requires_explicit_confirmation() -> None:
    arguments = build_parser().parse_args(["send", "--confirm-send"])

    assert arguments.confirm_send is True


def test_cli_resend_requires_explicit_flag() -> None:
    arguments = build_parser().parse_args(["send", "--confirm-send", "--allow-resend"])

    assert arguments.allow_resend is True
    assert arguments.bypass_review is False


def test_cli_send_review_bypass_is_explicit() -> None:
    arguments = build_parser().parse_args(["send", "--confirm-send", "--bypass-review"])

    assert arguments.bypass_review is True


def test_cli_rescore_is_dry_run_by_default() -> None:
    arguments = build_parser().parse_args(["rescore"])

    assert arguments.apply is False


def test_cli_rescore_apply_is_explicit() -> None:
    arguments = build_parser().parse_args(["rescore", "--apply"])

    assert arguments.apply is True


def test_cli_send_rejects_dry_run_and_confirmation_together() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["send", "--dry-run", "--confirm-send"])


def test_smtp_delivery_prompts_for_unstored_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ccip.cli.getpass.getpass", lambda prompt: "temporary-secret")

    result = smtp_config_for_delivery(
        SMTPConfig(host="smtp.example.com", username="sender@example.com")
    )

    assert result.password is not None
    assert result.password.get_secret_value() == "temporary-secret"


def test_smtp_delivery_rejects_empty_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ccip.cli.getpass.getpass", lambda prompt: "")

    with pytest.raises(RuntimeError, match="cannot be empty"):
        smtp_config_for_delivery(
            SMTPConfig(host="smtp.example.com", username="sender@example.com")
        )
