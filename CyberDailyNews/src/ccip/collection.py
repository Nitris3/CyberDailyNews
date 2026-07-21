"""Failure-isolated collector orchestration and source health reporting."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from time import sleep

import structlog

from ccip.domain import CollectedItem
from ccip.interfaces import Collector

logger = structlog.get_logger(__name__)


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    EMPTY = "empty"
    FAILED = "failed"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class SourceHealth:
    source: str
    status: HealthStatus
    item_count: int = 0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CollectionResult:
    items: tuple[CollectedItem, ...]
    sources: tuple[SourceHealth, ...]


class CollectionRunner:
    def __init__(
        self,
        collectors: tuple[Collector, ...],
        *,
        max_workers: int = 8,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 0.5,
        stale_after_days: int = 14,
    ) -> None:
        self.collectors = collectors
        self.max_workers = max_workers
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.stale_after_days = stale_after_days

    def run(self) -> CollectionResult:
        items: list[CollectedItem] = []
        health: list[SourceHealth] = []
        seen: set[tuple[str, str]] = set()
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = executor.map(self._collect, self.collectors)
        for collector, collected, collection_error in results:
            if collection_error is not None:
                health.append(
                    SourceHealth(collector.name, HealthStatus.FAILED, error=str(collection_error))
                )
                logger.warning(
                    "source_collection_failed",
                    source=collector.name,
                    error=str(collection_error),
                )
                continue
            try:
                unique = [item for item in collected if (item.source, item.external_id) not in seen]
                seen.update((item.source, item.external_id) for item in unique)
                items.extend(unique)
                stale_cutoff = datetime.now().astimezone() - timedelta(days=self.stale_after_days)
                status = (
                    HealthStatus.STALE
                    if unique and max(item.published_at for item in unique) < stale_cutoff
                    else HealthStatus.HEALTHY if unique else HealthStatus.EMPTY
                )
                health.append(SourceHealth(collector.name, status, len(unique)))
                logger.info(
                    "source_collection_completed",
                    source=collector.name,
                    status=status,
                    item_count=len(unique),
                )
            except Exception as error:
                health.append(SourceHealth(collector.name, HealthStatus.FAILED, error=str(error)))
                logger.warning(
                    "source_collection_failed",
                    source=collector.name,
                    error=str(error),
                    exc_info=True,
                )
        return CollectionResult(tuple(items), tuple(health))

    def _collect(
        self,
        collector: Collector,
    ) -> tuple[Collector, Sequence[CollectedItem], Exception | None]:
        error: Exception | None = None
        for attempt in range(self.retry_attempts + 1):
            try:
                return collector, collector.collect(), None
            except Exception as caught:
                error = caught
                if attempt < self.retry_attempts:
                    sleep(self.retry_backoff_seconds * (2**attempt))
        return collector, (), error
