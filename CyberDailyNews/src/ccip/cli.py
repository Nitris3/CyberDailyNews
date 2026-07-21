"""CCIP command-line entry point."""

from __future__ import annotations

import argparse
import getpass
import os
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from time import perf_counter

import structlog
from pydantic import SecretStr

from ccip.collection_status import record_rescore_seconds, write_collection_status
from ccip.collectors import KEVCollector, RSSCollector
from ccip.config import SMTPConfig, load_settings
from ccip.dashboard import run_dashboard
from ccip.db import Database, build_engine
from ccip.delivery import SMTPDelivery, compose_email
from ccip.interfaces import Collector
from ccip.logging import configure_logging
from ccip.pipeline import IngestionPipeline
from ccip.processors import RulesProcessor
from ccip.rendering import ReportRenderer
from ccip.reporting import DailyReportBuilder, open_preview, rewrite_report, write_preview
from ccip.repository import DeliveryRepository
from ccip.rescoring import rescore_articles
from ccip.summarization import OllamaSummarizer, Summarizer
from ccip.web_review import run_web_review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccip")
    parser.add_argument("--config", default="config/ccip.yml")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init-db", help="create the configured database schema")
    subcommands.add_parser("collect", help="collect, process, and store intelligence")
    subcommands.add_parser("dashboard", help="open the local browser dashboard")
    subcommands.add_parser("scheduled-run", help=argparse.SUPPRESS)
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
    send = subcommands.add_parser(
        "send",
        help="prepare an email; delivery requires the explicit --confirm-send flag",
    )
    send.add_argument("--date", type=date.fromisoformat, default=date.today())
    send.add_argument("--output", default=None, help="dry-run HTML output path")
    send.add_argument(
        "--resummarize",
        action="store_true",
        help="use the configured local Ollama model to simplify titles and summaries",
    )
    send.add_argument(
        "--allow-resend",
        action="store_true",
        help="explicitly allow another delivery for the same date and recipients",
    )
    delivery = send.add_mutually_exclusive_group()
    delivery.add_argument(
        "--dry-run",
        action="store_true",
        help="write a local preview without sending (the default)",
    )
    delivery.add_argument(
        "--confirm-send",
        action="store_true",
        help="actually deliver through the configured SMTP server",
    )
    send.add_argument(
        "--bypass-review",
        action="store_true",
        help="skip the interactive human review gate (requires --confirm-send)",
    )
    rescore = subcommands.add_parser(
        "rescore",
        help="preview score changes for stored articles",
    )
    rescore.add_argument(
        "--apply",
        action="store_true",
        help="persist recalculated scores and severities (default is dry run)",
    )
    return parser


def build_collectors(settings: object) -> tuple[Collector, ...]:
    from ccip.config import Settings

    if not isinstance(settings, Settings):
        raise TypeError("settings must be a Settings instance")
    collectors: list[Collector] = []
    for source in settings.sources:
        if source.name in settings.collection.disabled_sources:
            continue
        if source.kind == "rss":
            collectors.append(
                RSSCollector(source, timeout_seconds=settings.collection.source_timeout_seconds)
            )
        elif source.kind == "api":
            collectors.append(
                KEVCollector(
                    source,
                    timeout_seconds=settings.collection.source_timeout_seconds,
                    cache_path=Path("data/cisa-kev.cache.json"),
                    cache_hours=settings.collection.kev_cache_hours,
                )
            )
    return tuple(collectors)


def build_summarizer(settings: object) -> Summarizer | None:
    from ccip.config import Settings

    if not isinstance(settings, Settings):
        raise TypeError("settings must be a Settings instance")
    config = settings.summarization
    if config.provider == "ollama":
        return OllamaSummarizer(
            config.model,
            config.endpoint,
            config.timeout_seconds,
            config.audience,
            config.instructions,
        )
    return None


def smtp_config_for_delivery(config: SMTPConfig, credential: str | None = None) -> SMTPConfig:
    """Prompt for an unstored SMTP credential when authenticated delivery needs one."""
    if credential:
        return config.model_copy(update={"password": SecretStr(credential)})
    if not config.username or config.password is not None:
        return config
    password = getpass.getpass(f"SMTP credential for {config.username}: ")
    if not password:
        raise RuntimeError("SMTP credential cannot be empty")
    return config.model_copy(update={"password": SecretStr(password)})


def main(arguments: Sequence[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    if options.command == "dashboard":
        run_dashboard(options.config)
        return 0
    config_path = Path(options.config).resolve()
    if options.command == "scheduled-run":
        os.chdir(config_path.parent.parent)
    settings = load_settings(config_path)
    configure_logging(settings.app.log_level)
    database = Database(build_engine(settings.database.url, echo=settings.database.echo))
    if options.command in {"init-db", "collect", "scheduled-run", "preview", "send", "rescore"}:
        database.create_schema()
    if options.command in {"collect", "scheduled-run"}:
        result = IngestionPipeline(
            database,
            build_collectors(settings),
            RulesProcessor(
                # AI is deliberately reserved for the final report candidates.
                summarizer=None,
                fallback_on_error=settings.summarization.fallback_to_rules,
                scoring=settings.scoring,
            ),
            max_workers=settings.collection.max_workers,
            retention_days=settings.collection.retention_days,
            retry_attempts=settings.collection.retry_attempts,
            retry_backoff_seconds=settings.collection.retry_backoff_seconds,
            stale_after_days=settings.collection.stale_after_days,
        ).run()
        write_collection_status(result)
        structlog.get_logger(__name__).info(
            "collection_command_completed",
            stored=result.stored,
            failed_sources=sum(source.status == "failed" for source in result.sources),
            total_seconds=result.total_seconds,
        )
        if options.command == "scheduled-run":
            rescore_started = perf_counter()
            rescore_result = rescore_articles(
                database,
                settings.scoring,
                {source.name: source.priority for source in settings.sources},
                apply=True,
            )
            record_rescore_seconds(perf_counter() - rescore_started)
            structlog.get_logger(__name__).info(
                "scheduled_rescore_completed",
                examined=rescore_result.examined,
                changed=rescore_result.changed,
            )
    if options.command == "rescore":
        rescore_result = rescore_articles(
            database,
            settings.scoring,
            {source.name: source.priority for source in settings.sources},
            apply=options.apply,
        )
        structlog.get_logger(__name__).info(
            "article_rescore_completed",
            examined=rescore_result.examined,
            changed=rescore_result.changed,
            applied=options.apply,
        )
    if options.command == "preview":
        builder = DailyReportBuilder(
            database,
            max_items=settings.email.max_items,
            timezone_name=settings.report.timezone,
        )
        report = builder.build(options.date)
        if options.resummarize or settings.summarization.provider == "ollama":
            config = settings.summarization
            summarizer = OllamaSummarizer(
                config.model,
                config.endpoint,
                config.timeout_seconds,
                config.audience,
                config.instructions,
            )
            report = rewrite_report(
                report,
                summarizer,
                fallback_on_error=settings.summarization.fallback_to_rules,
            )
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
    if options.command == "send":
        builder = DailyReportBuilder(
            database,
            max_items=settings.email.max_items,
            timezone_name=settings.report.timezone,
        )
        report = builder.build(options.date)
        if options.resummarize or settings.summarization.provider == "ollama":
            config = settings.summarization
            report = rewrite_report(
                report,
                OllamaSummarizer(
                    config.model,
                    config.endpoint,
                    config.timeout_seconds,
                    config.audience,
                    config.instructions,
                ),
                fallback_on_error=config.fallback_to_rules,
            )
        renderer = ReportRenderer(
            settings.email.template_directory,
            html_template=settings.email.html_template,
            text_template=settings.email.text_template,
        )
        logger = structlog.get_logger(__name__)
        if options.confirm_send:
            if not report.items:
                raise RuntimeError("refusing to send an empty report")
            with database.session() as session:
                already_sent = DeliveryRepository(session).was_sent(
                    report.report_date, settings.email.recipients
                )
            if already_sent and not options.allow_resend:
                with database.session() as session:
                    DeliveryRepository(session).record_attempt(
                        report.report_date,
                        settings.email.recipients,
                        status="blocked",
                        item_count=len(report.items),
                        detail="Duplicate delivery prevented",
                    )
                raise RuntimeError(
                    "this report was already sent to these recipients; "
                    "use --allow-resend only when another delivery is intentional"
                )
            if not options.bypass_review:
                config = settings.summarization
                reviewed = run_web_review(
                    report,
                    renderer,
                    sender=settings.email.sender,
                    recipients=settings.email.recipients,
                    subject=renderer.render_subject(settings.email.subject, report),
                    credential_required=bool(
                        settings.email.smtp.username and settings.email.smtp.password is None
                    ),
                    rewrite=lambda candidate: rewrite_report(
                        candidate,
                        OllamaSummarizer(
                            config.model,
                            config.endpoint,
                            config.timeout_seconds,
                            config.audience,
                            config.instructions,
                        ),
                        fallback_on_error=config.fallback_to_rules,
                    ),
                )
                if reviewed is None:
                    with database.session() as session:
                        DeliveryRepository(session).record_attempt(
                            report.report_date,
                            settings.email.recipients,
                            status="denied",
                            item_count=len(report.items),
                            detail="Reviewer denied delivery",
                        )
                    logger.info(
                        "report_email_denied",
                        item_count=len(report.items),
                        report_date=report.report_date.isoformat(),
                    )
                    return 0
                report = reviewed.report
                review_credential = reviewed.credential
            else:
                review_credential = None
            message = compose_email(
                sender=settings.email.sender,
                recipients=settings.email.recipients,
                subject=renderer.render_subject(settings.email.subject, report),
                html=renderer.render_html(report),
                text=renderer.render_text(report),
            )
            try:
                SMTPDelivery(
                    smtp_config_for_delivery(settings.email.smtp, review_credential)
                ).deliver(message)
            except Exception as error:
                with database.session() as session:
                    DeliveryRepository(session).record_attempt(
                        report.report_date,
                        settings.email.recipients,
                        status="failed",
                        item_count=len(report.items),
                        detail=str(error),
                    )
                raise
            with database.session() as session:
                repository = DeliveryRepository(session)
                repository.record(report.report_date, settings.email.recipients)
                repository.record_attempt(
                    report.report_date,
                    settings.email.recipients,
                    status="sent",
                    item_count=len(report.items),
                )
            logger.info(
                "report_email_sent",
                recipient_count=len(settings.email.recipients),
                item_count=len(report.items),
                report_date=report.report_date.isoformat(),
            )
        else:
            output = options.output or f"reports/daily-news-{options.date.isoformat()}-dry-run.html"
            path = write_preview(renderer, report, output)
            logger.info(
                "report_email_dry_run",
                path=str(path),
                recipient_count=len(settings.email.recipients),
                item_count=len(report.items),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
