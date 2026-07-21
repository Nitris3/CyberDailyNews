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


class CountingProcessor(RulesProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def process(self, item: CollectedItem):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().process(item)


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


def test_existing_article_is_skipped_before_processing() -> None:
    database = Database(build_engine("sqlite+pysqlite:///:memory:"))
    database.create_schema()
    processor = CountingProcessor()
    pipeline = IngestionPipeline(database, (StaticCollector((collected_item(),)),), processor)

    pipeline.run()
    pipeline.run()

    assert processor.calls == 1
