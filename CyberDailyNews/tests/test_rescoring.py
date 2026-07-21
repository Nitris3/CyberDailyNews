from datetime import UTC, datetime

from ccip.config import ScoringConfig
from ccip.db import Database, build_engine
from ccip.domain import IntelligenceItem, Severity
from ccip.repository import ArticleRepository
from ccip.rescoring import rescore_articles


def database_with_article() -> Database:
    database = Database(build_engine("sqlite+pysqlite:///:memory:"))
    database.create_schema()
    with database.session() as session:
        ArticleRepository(session).add(
            IntelligenceItem(
                "1",
                "Vendor Feed",
                "ExampleCorp security update",
                "https://example.com",
                datetime(2026, 7, 20, tzinfo=UTC),
                "A routine product update.",
                "Vendor Advisories",
                Severity.LOW,
                1.0,
            )
        )
    return database


def test_rescore_dry_run_does_not_change_database() -> None:
    database = database_with_article()
    policy = ScoringConfig(
        watchlist_keywords=("ExampleCorp",), watchlist_bonus=3
    )

    result = rescore_articles(database, policy, {"Vendor Feed": 5})

    assert result.examined == 1
    assert result.changed == 1
    with database.session() as session:
        assert ArticleRepository(session).all()[0].score == 1.0


def test_rescore_apply_updates_score_and_severity() -> None:
    database = database_with_article()
    policy = ScoringConfig(
        watchlist_keywords=("ExampleCorp",), watchlist_bonus=3
    )

    result = rescore_articles(database, policy, {"Vendor Feed": 5}, apply=True)

    assert result.changed == 1
    with database.session() as session:
        updated = ArticleRepository(session).all()[0]
    assert updated.score == 9.0
    assert updated.severity is Severity.CRITICAL
