"""Daily report selection and preview generation."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from ccip.db import Database
from ccip.domain import DailyReport
from ccip.rendering import ReportRenderer
from ccip.repository import ArticleRepository


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
