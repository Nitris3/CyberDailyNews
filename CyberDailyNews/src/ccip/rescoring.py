"""Recalculate persisted article rankings from the current scoring policy."""

from __future__ import annotations

from dataclasses import dataclass

from ccip.config import ScoringConfig
from ccip.db import Database
from ccip.domain import CollectedItem
from ccip.processors import RulesProcessor
from ccip.repository import ArticleRepository


@dataclass(frozen=True, slots=True)
class RescoreResult:
    examined: int
    changed: int


def rescore_articles(
    database: Database,
    scoring: ScoringConfig,
    source_priorities: dict[str, int],
    *,
    apply: bool = False,
) -> RescoreResult:
    """Preview or apply score/severity changes without collection or AI."""
    processor = RulesProcessor(scoring=scoring)
    examined = 0
    changed = 0
    with database.session() as session:
        repository = ArticleRepository(session)
        for existing in repository.all():
            examined += 1
            candidate = processor.process(
                CollectedItem(
                    external_id=existing.external_id,
                    source=existing.source,
                    title=existing.title,
                    url=existing.url,
                    published_at=existing.published_at,
                    content=existing.summary,
                    category=existing.category,
                    metadata={"priority": source_priorities.get(existing.source, 3)},
                )
            )
            if candidate is None:
                continue
            if candidate.score == existing.score and candidate.severity is existing.severity:
                continue
            changed += 1
            if apply:
                repository.update_ranking(
                    existing.source,
                    existing.external_id,
                    score=candidate.score,
                    severity=candidate.severity,
                )
    return RescoreResult(examined=examined, changed=changed)
