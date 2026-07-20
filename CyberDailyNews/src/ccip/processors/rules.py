"""Deterministic normalization, summarization, and priority scoring."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

import structlog

from ccip.domain import CollectedItem, IntelligenceItem, Severity
from ccip.summarization import Summarizer

logger = structlog.get_logger(__name__)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class RulesProcessor:
    def __init__(
        self,
        *,
        summary_length: int = 600,
        summarizer: Summarizer | None = None,
        fallback_on_error: bool = True,
    ) -> None:
        if summary_length < 50:
            raise ValueError("summary_length must be at least 50")
        self.summary_length = summary_length
        self.summarizer = summarizer
        self.fallback_on_error = fallback_on_error

    def process(self, item: CollectedItem) -> IntelligenceItem | None:
        summary = self._plain_text(item.content)
        if not summary:
            summary = item.title
        summary = self._truncate(summary)
        if self.summarizer is not None:
            try:
                generated = self.summarizer.summarize(
                    title=self._plain_text(item.title),
                    content=summary,
                    max_characters=self.summary_length,
                )
                if generated.strip():
                    summary = self._truncate(self._plain_text(generated))
            except Exception as error:
                if not self.fallback_on_error:
                    raise
                logger.warning(
                    "generative_summary_failed",
                    source=item.source,
                    external_id=item.external_id,
                    error=str(error),
                )
        score = self._score(item, summary)
        return IntelligenceItem(
            external_id=item.external_id,
            source=item.source,
            title=self._plain_text(item.title),
            url=item.url,
            published_at=item.published_at,
            summary=summary,
            category=item.category,
            severity=self._severity(score),
            score=score,
        )

    @staticmethod
    def _plain_text(value: str) -> str:
        parser = _TextExtractor()
        parser.feed(value)
        parser.close()
        return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()

    def _truncate(self, value: str) -> str:
        if len(value) <= self.summary_length:
            return value
        shortened = value[: self.summary_length - 1].rsplit(" ", 1)[0]
        return f"{shortened}…"

    @staticmethod
    def _score(item: CollectedItem, summary: str) -> float:
        priority = item.metadata.get("priority", 3)
        base = float(priority) * 1.2 if isinstance(priority, int | float) else 3.6
        text = f"{item.title} {summary} {item.category}".lower()
        if "exploited vulnerabilit" in text or "known exploited" in text:
            base += 2.0
        if item.metadata.get("known_ransomware_use") is True or "ransomware" in text:
            base += 1.5
        if any(term in text for term in ("critical", "remote code execution", "zero-day")):
            base += 1.0
        return round(min(base, 10.0), 1)

    @staticmethod
    def _severity(score: float) -> Severity:
        if score >= 9:
            return Severity.CRITICAL
        if score >= 7:
            return Severity.HIGH
        if score >= 4:
            return Severity.MEDIUM
        if score > 0:
            return Severity.LOW
        return Severity.INFORMATIONAL
