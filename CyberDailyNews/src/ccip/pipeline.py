"""Collection, processing, deduplication, and persistence orchestration."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from ccip.collection import CollectionRunner, SourceHealth
from ccip.db import Database
from ccip.interfaces import Collector, Processor
from ccip.repository import ArticleRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    collected: int
    processed: int
    stored: int
    skipped: int
    sources: tuple[SourceHealth, ...]


class IngestionPipeline:
    def __init__(
        self,
        database: Database,
        collectors: tuple[Collector, ...],
        processor: Processor,
    ) -> None:
        self.database = database
        self.collectors = collectors
        self.processor = processor

    def run(self) -> IngestionResult:
        collection = CollectionRunner(self.collectors).run()
        processed = 0
        stored = 0
        skipped = 0
        with self.database.session() as session:
            repository = ArticleRepository(session)
            for collected_item in collection.items:
                item = self.processor.process(collected_item)
                if item is None:
                    skipped += 1
                    continue
                processed += 1
                if repository.exists(item.source, item.external_id):
                    skipped += 1
                    continue
                repository.add(item)
                stored += 1
        result = IngestionResult(
            collected=len(collection.items),
            processed=processed,
            stored=stored,
            skipped=skipped,
            sources=collection.sources,
        )
        logger.info(
            "ingestion_completed",
            collected=result.collected,
            processed=result.processed,
            stored=result.stored,
            skipped=result.skipped,
        )
        return result

