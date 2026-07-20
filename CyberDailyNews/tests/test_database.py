from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from ccip.db import Database, build_engine
from ccip.domain import IntelligenceItem, Severity
from ccip.repository import ArticleRepository


def make_item(external_id: str = "article-1") -> IntelligenceItem:
    return IntelligenceItem(
        external_id=external_id,
        source="Test Source",
        title="Important security news",
        url="https://example.com/article",
        published_at=datetime(2026, 7, 20, 12, tzinfo=UTC),
        summary="A concise intelligence summary.",
        category="Threat Intelligence",
        severity=Severity.HIGH,
        score=8.5,
    )


def test_repository_round_trip_and_query_order() -> None:
    database = Database(build_engine("sqlite+pysqlite:///:memory:"))
    database.create_schema()

    with database.session() as session:
        repository = ArticleRepository(session)
        repository.add(make_item("lower-score"))
        higher = make_item("higher-score")
        repository.add(
            IntelligenceItem(
                external_id=higher.external_id,
                source=higher.source,
                title=higher.title,
                url=higher.url,
                published_at=higher.published_at,
                summary=higher.summary,
                category=higher.category,
                severity=Severity.CRITICAL,
                score=9.9,
            )
        )
        assert repository.exists("Test Source", "higher-score")
        results = repository.published_between(
            higher.published_at - timedelta(hours=1), higher.published_at + timedelta(hours=1)
        )

    assert [item.external_id for item in results] == ["higher-score", "lower-score"]
    assert results[0].severity is Severity.CRITICAL


def test_database_session_rolls_back_on_constraint_error() -> None:
    database = Database(build_engine("sqlite+pysqlite:///:memory:"))
    database.create_schema()

    with pytest.raises(IntegrityError), database.session() as session:
        repository = ArticleRepository(session)
        repository.add(make_item())
        repository.add(make_item())

    with database.session() as session:
        assert not ArticleRepository(session).exists("Test Source", "article-1")

