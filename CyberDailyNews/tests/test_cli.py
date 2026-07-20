from ccip.cli import build_parser


def test_cli_parses_database_initialization() -> None:
    arguments = build_parser().parse_args(["--config", "custom.yml", "init-db"])

    assert arguments.config == "custom.yml"
    assert arguments.command == "init-db"

