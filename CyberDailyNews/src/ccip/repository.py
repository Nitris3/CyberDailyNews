"""Article repository."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ccip.db import ArticleRecord, DeliveryRecord
from ccip.domain import IntelligenceItem, Severity


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

    def identities(self) -> set[tuple[str, str]]:
        """Return lightweight keys so duplicate checks happen before expensive processing."""
        statement = select(ArticleRecord.source, ArticleRecord.external_id)
        return set(self.session.execute(statement).tuples())

    def published_between(self, start: datetime, end: datetime) -> list[IntelligenceItem]:
        statement = (
            select(ArticleRecord)
            .where(ArticleRecord.published_at >= start, ArticleRecord.published_at < end)
            .order_by(ArticleRecord.score.desc(), ArticleRecord.published_at.desc())
        )
        return [record.to_domain() for record in self.session.scalars(statement)]

    def all(self) -> list[IntelligenceItem]:
        statement = select(ArticleRecord).order_by(ArticleRecord.published_at.desc())
        return [record.to_domain() for record in self.session.scalars(statement)]

    def update_ranking(
        self, source: str, external_id: str, *, score: float, severity: Severity
    ) -> None:
        statement = select(ArticleRecord).where(
            ArticleRecord.source == source,
            ArticleRecord.external_id == external_id,
        )
        record = self.session.scalar(statement)
        if record is None:
            raise LookupError(f"article not found: {source}/{external_id}")
        record.score = score
        record.severity = severity.value


class DeliveryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def recipient_key(recipients: Sequence[str]) -> str:
        return ",".join(sorted(address.strip().casefold() for address in recipients))

    def was_sent(self, report_date: date, recipients: Sequence[str]) -> bool:
        statement = select(DeliveryRecord.id).where(
            DeliveryRecord.report_date == report_date,
            DeliveryRecord.recipient_key == self.recipient_key(recipients),
        )
        return self.session.scalar(statement) is not None

    def record(self, report_date: date, recipients: Sequence[str]) -> None:
        self.session.add(
            DeliveryRecord(
                report_date=report_date,
                recipient_key=self.recipient_key(recipients),
            )
        )
