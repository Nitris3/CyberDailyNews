from collections.abc import Sequence
from datetime import UTC, datetime

from ccip.db import Database, build_engine
from ccip.domain import CollectedItem
from ccip.pipeline import IngestionPipeline
from ccip.processors import RulesProcessor


class StaticCollector:
    name = "Static"

    def __init__(self, items: Sequence[CollectedItem]) -> None:
        self.items = items

    def collect(self) -> Sequence[CollectedItem]:
        return self.items


def collected_item() -> CollectedItem:
    return CollectedItem(
        external_id="item-1",
        source="Static",
        title="Security update",
        url="https://example.com/1",
        published_at=datetime(2026, 7, 20, tzinfo=UTC),
        content="Install the security update.",
        category="Vendor Advisories",
        metadata={"priority": 4},
    )


def test_ingestion_pipeline_persists_once_across_repeated_runs() -> None:
    database = Database(build_engine("sqlite+pysqlite:///:memory:"))
    database.create_schema()
    pipeline = IngestionPipeline(
        database,
        (StaticCollector((collected_item(),)),),
        RulesProcessor(),
    )

    first = pipeline.run()
    second = pipeline.run()

    assert first.stored == 1
    assert first.skipped == 0
    assert second.stored == 0
    assert second.skipped == 1
