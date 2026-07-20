"""Article repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ccip.db import ArticleRecord
from ccip.domain import IntelligenceItem


class ArticleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: IntelligenceItem) -> ArticleRecord:
        record = ArticleRecord.from_domain(item)
        self.session.add(record)
        self.session.flush()
        return record

    def exists(self, source: str, external_id: str) -> bool:
        statement = select(ArticleRecord.id).where(
            ArticleRecord.source == source,
            ArticleRecord.external_id == external_id,
        )
        return self.session.scalar(statement) is not None

    def published_between(self, start: datetime, end: datetime) -> list[IntelligenceItem]:
        statement = (
            select(ArticleRecord)
            .where(ArticleRecord.published_at >= start, ArticleRecord.published_at < end)
            .order_by(ArticleRecord.score.desc(), ArticleRecord.published_at.desc())
        )
        return [record.to_domain() for record in self.session.scalars(statement)]

