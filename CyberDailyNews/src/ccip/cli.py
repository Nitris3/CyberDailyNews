"""CCIP command-line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date

import structlog

from ccip.collectors import KEVCollector, RSSCollector
from ccip.config import load_settings
from ccip.db import Database, build_engine
from ccip.interfaces import Collector
from ccip.logging import configure_logging
from ccip.pipeline import IngestionPipeline
from ccip.processors import RulesProcessor
from ccip.rendering import ReportRenderer
from ccip.reporting import DailyReportBuilder, open_preview, rewrite_report, write_preview
from ccip.summarization import CopilotCLISummarizer, OllamaSummarizer, Summarizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccip")
    parser.add_argument("--config", default="config/ccip.yml")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init-db", help="create the configured database schema")
    subcommands.add_parser("collect", help="collect, process, and store intelligence")
    preview = subcommands.add_parser("preview", help="render a daily HTML report without sending")
    preview.add_argument("--date", type=date.fromisoformat, default=date.today())
    preview.add_argument("--output", default=None)
    preview.add_argument(
        "--open",
        action="store_true",
        help="open the rendered report in the default browser (never sends email)",
    )
    preview.add_argument(
        "--resummarize",
        action="store_true",
        help="use the configured local Ollama model to simplify titles and summaries",
    )
    return parser


def build_collectors(settings: object) -> tuple[Collector, ...]:
    from ccip.config import Settings

    if not isinstance(settings, Settings):
        raise TypeError("settings must be a Settings instance")
    collectors: list[Collector] = []
    for source in settings.sources:
        if source.kind == "rss":
            collectors.append(RSSCollector(source))
        elif source.kind == "api":
            collectors.append(KEVCollector(source))
    return tuple(collectors)


def build_summarizer(settings: object) -> Summarizer | None:
    from ccip.config import Settings

    if not isinstance(settings, Settings):
        raise TypeError("settings must be a Settings instance")
    config = settings.summarization
    if config.provider == "ollama":
        return OllamaSummarizer(config.model, config.endpoint, config.timeout_seconds)
    if config.provider == "copilot":
        return CopilotCLISummarizer(config.model, config.copilot_binary, config.timeout_seconds)
    return None


def main(arguments: Sequence[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    settings = load_settings(options.config)
    configure_logging(settings.app.log_level)
    database = Database(build_engine(settings.database.url, echo=settings.database.echo))
    if options.command in {"init-db", "collect", "preview"}:
        database.create_schema()
    if options.command == "collect":
        result = IngestionPipeline(
            database,
            build_collectors(settings),
            RulesProcessor(
                summarizer=build_summarizer(settings),
                fallback_on_error=settings.summarization.fallback_to_rules,
            ),
        ).run()
        structlog.get_logger(__name__).info(
            "collection_command_completed",
            stored=result.stored,
            failed_sources=sum(source.status == "failed" for source in result.sources),
        )
    if options.command == "preview":
        builder = DailyReportBuilder(database, max_items=settings.email.max_items)
        report = builder.build(options.date)
        if options.resummarize:
            config = settings.summarization
            summarizer = OllamaSummarizer(
                config.model,
                config.endpoint,
                config.timeout_seconds,
            )
            report = rewrite_report(report, summarizer)
        renderer = ReportRenderer(
            settings.email.template_directory,
            html_template=settings.email.html_template,
            text_template=settings.email.text_template,
        )
        output = options.output or f"reports/daily-news-{options.date.isoformat()}.html"
        path = write_preview(renderer, report, output)
        if options.open:
            open_preview(path)
        structlog.get_logger(__name__).info(
            "report_preview_written",
            path=str(path),
            item_count=len(report.items),
            opened=options.open,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
