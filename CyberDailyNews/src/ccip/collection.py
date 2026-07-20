"""Failure-isolated collector orchestration and source health reporting."""

from __future__ import annotations

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
    def __init__(self, collectors: tuple[Collector, ...]) -> None:
        self.collectors = collectors

    def run(self) -> CollectionResult:
        items: list[CollectedItem] = []
        health: list[SourceHealth] = []
        seen: set[tuple[str, str]] = set()
        for collector in self.collectors:
            try:
                collected = collector.collect()
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

