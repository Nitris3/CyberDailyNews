"""SQLAlchemy engine, unit-of-work, and persistence models."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, UniqueConstraint, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from ccip.domain import IntelligenceItem, Severity


class Base(DeclarativeBase):
    pass


class ArticleRecord(Base):
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(1000))
    url: Mapped[str] = mapped_column(String(2048))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    summary: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(255), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now().astimezone()
    )

    @classmethod
    def from_domain(cls, item: IntelligenceItem) -> ArticleRecord:
        return cls(
            external_id=item.external_id,
            source=item.source,
            title=item.title,
            url=item.url,
            published_at=item.published_at,
            summary=item.summary,
            category=item.category,
            severity=item.severity.value,
            score=item.score,
        )

    def to_domain(self) -> IntelligenceItem:
        return IntelligenceItem(
            external_id=self.external_id,
            source=self.source,
            title=self.title,
            url=self.url,
            published_at=self.published_at,
            summary=self.summary,
            category=self.category,
            severity=Severity(self.severity),
            score=self.score,
        )


def build_engine(url: str, *, echo: bool = False) -> Engine:
    return create_engine(url, echo=echo)


class Database:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

