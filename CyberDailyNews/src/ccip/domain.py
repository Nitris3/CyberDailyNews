"""Transport-independent domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class Severity(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class CollectedItem:
    external_id: str
    source: str
    title: str
    url: str
    published_at: datetime
    content: str
    category: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IntelligenceItem:
    external_id: str
    source: str
    title: str
    url: str
    published_at: datetime
    summary: str
    category: str
    severity: Severity = Severity.INFORMATIONAL
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class DailyReport:
    report_date: date
    items: tuple[IntelligenceItem, ...]

