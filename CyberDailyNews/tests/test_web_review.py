from datetime import UTC, date, datetime

from ccip.domain import DailyReport, IntelligenceItem
from ccip.web_review import update_report


def test_browser_form_edits_removes_and_reorders_articles() -> None:
    items = tuple(
        IntelligenceItem(
            str(i),
            "Source",
            f"Title {i}",
            f"https://{i}",
            datetime(2026, 7, 20, tzinfo=UTC),
            f"Summary {i}",
            "News",
        )
        for i in range(3)
    )
    report = DailyReport(date(2026, 7, 20), items)

    result = update_report(
        report,
        {
            "order": ["2,0,1"],
            "include_2": ["yes"],
            "title_2": ["Updated"],
            "summary_2": ["Updated summary"],
            "include_0": ["yes"],
        },
    )

    assert [item.external_id for item in result.items] == ["2", "0"]
    assert result.items[0].title == "Updated"
