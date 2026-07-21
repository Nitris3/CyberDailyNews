"""Collection, processing, deduplication, and persistence orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

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
    collection_seconds: float
    processing_seconds: float
    total_seconds: float


class IngestionPipeline:
    def __init__(
        self,
        database: Database,
        collectors: tuple[Collector, ...],
        processor: Processor,
        *,
        max_workers: int = 8,
    ) -> None:
        self.database = database
        self.collectors = collectors
        self.processor = processor
        self.max_workers = max_workers

    def run(self) -> IngestionResult:
        started = perf_counter()
        collection = CollectionRunner(self.collectors, max_workers=self.max_workers).run()
        collected_at = perf_counter()
        processed = 0
        stored = 0
        skipped = 0
        with self.database.session() as session:
            repository = ArticleRepository(session)
            existing = repository.identities()
            for collected_item in collection.items:
                identity = (collected_item.source, collected_item.external_id)
                if identity in existing:
                    skipped += 1
                    continue
                item = self.processor.process(collected_item)
                if item is None:
                    skipped += 1
                    continue
                processed += 1
                repository.add(item)
                existing.add(identity)
                stored += 1
        finished = perf_counter()
        result = IngestionResult(
            collected=len(collection.items),
            processed=processed,
            stored=stored,
            skipped=skipped,
            sources=collection.sources,
            collection_seconds=round(collected_at - started, 2),
            processing_seconds=round(finished - collected_at, 2),
            total_seconds=round(finished - started, 2),
        )
        logger.info(
            "ingestion_completed",
            collected=result.collected,
            processed=result.processed,
            stored=result.stored,
            skipped=result.skipped,
            collection_seconds=result.collection_seconds,
            processing_seconds=result.processing_seconds,
            total_seconds=result.total_seconds,
        )
        return result
