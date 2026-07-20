from datetime import UTC, date, datetime
from pathlib import Path

from ccip.domain import DailyReport, IntelligenceItem, Severity
from ccip.rendering import ReportRenderer


def test_renderer_escapes_untrusted_content_and_builds_subject() -> None:
    template_directory = Path(__file__).parents[1] / "templates" / "email"
    renderer = ReportRenderer(template_directory)
    item = IntelligenceItem(
        external_id="1",
        source="Source",
        title="<script>alert(1)</script>",
        url="https://example.com/article",
        published_at=datetime(2026, 7, 20, tzinfo=UTC),
        summary="Summary & analysis",
        category="News",
        severity=Severity.HIGH,
        score=8.0,
    )
    report = DailyReport(date(2026, 7, 20), (item,))

    html = renderer.render_html(report)

    assert "&lt;script&gt;" in html
    assert "Summary &amp; analysis" in html
    subject = renderer.render_subject("Daily Report - {{ report_date }}", report)
    assert subject == "Daily Report - 2026-07-20"
