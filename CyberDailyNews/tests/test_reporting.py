from datetime import UTC, date, datetime
from pathlib import Path

from ccip.db import Database, build_engine
from ccip.domain import IntelligenceItem
from ccip.rendering import ReportRenderer
from ccip.reporting import DailyReportBuilder, unique_articles, write_preview
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


def test_report_deduplicates_similar_stories_and_keeps_highest_ranked() -> None:
    first = IntelligenceItem(
        "1",
        "Source A",
        "Microsoft fixes critical zero-day vulnerability",
        "https://a.example/story?ref=rss",
        datetime(2026, 7, 20, 12, tzinfo=UTC),
        "First",
        "News",
        score=9,
    )
    duplicate = IntelligenceItem(
        "2",
        "Source B",
        "Microsoft fixes a critical zero day vulnerability update",
        "https://b.example/report",
        datetime(2026, 7, 20, 13, tzinfo=UTC),
        "Second",
        "News",
        score=7,
    )

    assert unique_articles([first, duplicate]) == [first]


def test_report_deduplicates_differently_worded_versions_of_same_incident() -> None:
    first = IntelligenceItem(
        "1",
        "Source A",
        "Qilin Ransomware Attackers Exploit PAN-OS Authentication Bypass",
        "https://a.example/story",
        datetime(2026, 7, 21, tzinfo=UTC),
        "Threat actors exploited PAN-OS authentication bypass to deploy Qilin ransomware.",
        "News",
        score=10,
    )
    duplicate = IntelligenceItem(
        "2",
        "Source B",
        "Critical Palo Alto VPN bug exploited by Qilin ransomware gang",
        "https://b.example/report",
        datetime(2026, 7, 21, tzinfo=UTC),
        "Qilin breached networks through a PAN-OS GlobalProtect authentication bypass.",
        "News",
        score=10,
    )

    assert unique_articles([first, duplicate]) == [first]
