from datetime import UTC, date, datetime
from pathlib import Path

from ccip.db import Database, build_engine
from ccip.domain import IntelligenceItem
from ccip.rendering import ReportRenderer
from ccip.reporting import DailyReportBuilder, write_preview
from ccip.repository import ArticleRepository


def test_daily_report_selects_requested_date_and_writes_preview(tmp_path: Path) -> None:
    database = Database(build_engine("sqlite+pysqlite:///:memory:"))
    database.create_schema()
    with database.session() as session:
        ArticleRepository(session).add(
            IntelligenceItem(
                external_id="1",
                source="Source",
                title="Issue",
                url="https://example.com",
                published_at=datetime(2026, 7, 20, 12, tzinfo=UTC),
                summary="Summary",
                category="News",
                score=7.5,
            )
        )

    report = DailyReportBuilder(database).build(date(2026, 7, 20))
    renderer = ReportRenderer(Path(__file__).parents[1] / "templates" / "email")
    output = write_preview(renderer, report, tmp_path / "nested" / "preview.html")

    assert len(report.items) == 1
    assert output.exists()
    assert "Issue" in output.read_text(encoding="utf-8")
