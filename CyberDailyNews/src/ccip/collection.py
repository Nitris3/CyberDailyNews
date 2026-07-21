"""Failure-isolated collector orchestration and source health reporting."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum

import structlog

from ccip.domain import CollectedItem
from ccip.interfaces import Collector

logger = structlog.get_logger(__name__)


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    EMPTY = "empty"
    FAILED = "failed"


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
    def __init__(self, collectors: tuple[Collector, ...], *, max_workers: int = 8) -> None:
        self.collectors = collectors
        self.max_workers = max_workers

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
                status = HealthStatus.HEALTHY if unique else HealthStatus.EMPTY
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

    @staticmethod
    def _collect(
        collector: Collector,
    ) -> tuple[Collector, Sequence[CollectedItem], Exception | None]:
        try:
            return collector, collector.collect(), None
        except Exception as error:
            return collector, (), error
