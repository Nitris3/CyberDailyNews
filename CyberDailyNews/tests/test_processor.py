from datetime import UTC, datetime

from ccip.config import ScoringConfig
from ccip.domain import CollectedItem, Severity
from ccip.processors import RulesProcessor


class StaticSummarizer:
    def summarize(self, *, title: str, content: str, max_characters: int) -> str:
        return "Generated security summary."


class FailingSummarizer:
    def summarize(self, *, title: str, content: str, max_characters: int) -> str:
        raise RuntimeError("model unavailable")


def item(**changes: object) -> CollectedItem:
    values: dict[str, object] = {
        "external_id": "CVE-2026-1234",
        "source": "Source",
        "title": "Critical remote code execution",
        "url": "https://example.com",
        "published_at": datetime(2026, 7, 20, tzinfo=UTC),
        "content": "<p>Attackers are exploiting this issue &amp; deploying ransomware.</p>",
        "category": "Exploited Vulnerabilities",
        "metadata": {"priority": 5, "known_ransomware_use": True},
    }
    values.update(changes)
    return CollectedItem(**values)  # type: ignore[arg-type]


def test_rules_processor_cleans_html_and_scores_actionable_item() -> None:
    result = RulesProcessor().process(item())

    assert result is not None
    assert result.summary == "Attackers are exploiting this issue & deploying ransomware."
    assert result.severity is Severity.CRITICAL
    assert result.score == 10.0


def test_rules_processor_truncates_summary_on_word_boundary() -> None:
    result = RulesProcessor(summary_length=50).process(item(content="word " * 30))

    assert result is not None
    assert len(result.summary) <= 50
    assert result.summary.endswith("…")


def test_rules_processor_uses_generative_summary() -> None:
    result = RulesProcessor(summarizer=StaticSummarizer()).process(item())

    assert result is not None
    assert result.summary == "Generated security summary."


def test_rules_processor_falls_back_when_model_is_unavailable() -> None:
    result = RulesProcessor(summarizer=FailingSummarizer()).process(item())

    assert result is not None
    assert "Attackers are exploiting" in result.summary


def test_scoring_policy_and_company_watchlists_are_configurable() -> None:
    scoring = ScoringConfig(
        priority_multiplier=1,
        known_exploited_bonus=0,
        ransomware_bonus=0,
        critical_keyword_bonus=0,
        medium_threshold=2,
        high_threshold=4,
        critical_threshold=6,
        max_score=8,
        watchlist_keywords=("ExampleCorp",),
        watchlist_bonus=3,
    )

    result = RulesProcessor(scoring=scoring).process(
        item(title="ExampleCorp advisory", metadata={"priority": 2})
    )

    assert result is not None
    assert result.score == 5
    assert result.severity is Severity.HIGH


def test_watchlist_bonus_applies_once_when_multiple_terms_match() -> None:
    scoring = ScoringConfig(
        watchlist_keywords=("ExampleCorp", "Product X"),
        watchlist_bonus=2,
    )

    result = RulesProcessor(scoring=scoring).process(
        item(title="ExampleCorp Product X update", metadata={"priority": 1})
    )

    assert result is not None
    assert result.score == 6.7
