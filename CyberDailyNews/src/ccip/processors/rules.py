"""Deterministic normalization, summarization, and priority scoring."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

import structlog

from ccip.config import ScoringConfig
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
        scoring: ScoringConfig | None = None,
    ) -> None:
        if summary_length < 50:
            raise ValueError("summary_length must be at least 50")
        self.summary_length = summary_length
        self.summarizer = summarizer
        self.fallback_on_error = fallback_on_error
        self.scoring = scoring or ScoringConfig()

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

    def _score(self, item: CollectedItem, summary: str) -> float:
        config = self.scoring
        priority = item.metadata.get("priority", 3)
        base = (
            float(priority) * config.priority_multiplier
            if isinstance(priority, int | float)
            else 3 * config.priority_multiplier
        )
        text = f"{item.title} {summary} {item.category} {item.source}".lower()
        if any(term.lower() in text for term in config.exploited_keywords):
            base += config.known_exploited_bonus
        if item.metadata.get("known_ransomware_use") is True or any(
            term.lower() in text for term in config.ransomware_keywords
        ):
            base += config.ransomware_bonus
        if any(term.lower() in text for term in config.critical_keywords):
            base += config.critical_keyword_bonus
        if any(term.strip("'\"").lower() in text for term in config.watchlist_keywords):
            base += config.watchlist_bonus
        return round(min(base, config.max_score), 1)

    def _severity(self, score: float) -> Severity:
        if score >= self.scoring.critical_threshold:
            return Severity.CRITICAL
        if score >= self.scoring.high_threshold:
            return Severity.HIGH
        if score >= self.scoring.medium_threshold:
            return Severity.MEDIUM
        if score > 0:
            return Severity.LOW
        return Severity.INFORMATIONAL
