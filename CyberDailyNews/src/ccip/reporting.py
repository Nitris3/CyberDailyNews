"""Daily report selection and preview generation."""

from __future__ import annotations

import webbrowser
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from ccip.db import Database
from ccip.domain import DailyReport
from ccip.rendering import ReportRenderer
from ccip.repository import ArticleRepository
from ccip.summarization import OllamaSummarizer


class DailyReportBuilder:
    def __init__(self, database: Database, *, max_items: int = 25) -> None:
        self.database = database
        self.max_items = max_items

    def build(self, report_date: date) -> DailyReport:
        start = datetime.combine(report_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        with self.database.session() as session:
            items = ArticleRepository(session).published_between(start, end)
        return DailyReport(report_date, tuple(items[: self.max_items]))


def write_preview(renderer: ReportRenderer, report: DailyReport, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(renderer.render_html(report), encoding="utf-8")
    return path.resolve()


def open_preview(path: str | Path) -> bool:
    """Open a generated preview in the system's default web browser."""
    return webbrowser.open(Path(path).resolve().as_uri())


def rewrite_report(report: DailyReport, summarizer: OllamaSummarizer) -> DailyReport:
    """Rewrite display copy without changing persisted source records."""
    rewritten = []
    for item in report.items:
        brief = summarizer.rewrite_brief(title=item.title, content=item.summary)
        rewritten.append(replace(item, title=brief.title, summary=brief.summary))
    return replace(report, items=tuple(rewritten))
