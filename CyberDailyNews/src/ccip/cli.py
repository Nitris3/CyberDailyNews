"""CCIP command-line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from ccip.config import load_settings
from ccip.db import Database, build_engine
from ccip.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccip")
    parser.add_argument("--config", default="config/ccip.yml")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init-db", help="create the configured database schema")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    settings = load_settings(options.config)
    configure_logging(settings.app.log_level)
    if options.command == "init-db":
        database = Database(build_engine(settings.database.url, echo=settings.database.echo))
        database.create_schema()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

