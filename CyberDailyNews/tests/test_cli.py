from ccip.cli import build_parser


def test_cli_parses_database_initialization() -> None:
    arguments = build_parser().parse_args(["--config", "custom.yml", "init-db"])

    assert arguments.config == "custom.yml"
    assert arguments.command == "init-db"


def test_cli_parses_collection_command() -> None:
    arguments = build_parser().parse_args(["collect"])

    assert arguments.command == "collect"


def test_cli_parses_preview_date_and_output() -> None:
    arguments = build_parser().parse_args(
        ["preview", "--date", "2026-07-20", "--output", "report.html"]
    )

    assert arguments.date.isoformat() == "2026-07-20"
    assert arguments.output == "report.html"
