"""Daily report selection and preview generation."""

from __future__ import annotations

import re
import webbrowser
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from ccip.db import Database
from ccip.domain import DailyReport, IntelligenceItem
from ccip.rendering import ReportRenderer
from ccip.repository import ArticleRepository
from ccip.summarization import OllamaSummarizer


class DailyReportBuilder:
    def __init__(
        self, database: Database, *, max_items: int = 25, timezone_name: str = "local"
    ) -> None:
        self.database = database
        self.max_items = max_items
        self.timezone_name = timezone_name

    def build(self, report_date: date) -> DailyReport:
        timezone = (
            datetime.now().astimezone().tzinfo
            if self.timezone_name == "local"
            else ZoneInfo(self.timezone_name)
        )
        start = datetime.combine(report_date, time.min, tzinfo=timezone).astimezone(UTC)
        end = (
            datetime.combine(report_date, time.min, tzinfo=timezone) + timedelta(days=1)
        ).astimezone(UTC)
        with self.database.session() as session:
            items = ArticleRepository(session).published_between(start, end)
        return DailyReport(report_date, tuple(unique_articles(items)[: self.max_items]))


def unique_articles(items: list[IntelligenceItem]) -> list[IntelligenceItem]:
    """Keep the highest-ranked representation of each story across sources."""
    selected: list[IntelligenceItem] = []
    urls: set[str] = set()
    titles: list[str] = []
    story_terms: list[set[str]] = []
    for candidate in items:
        url = _canonical_url(candidate.url)
        title = _normalized_title(candidate.title)
        terms = _story_terms(candidate.title, candidate.summary)
        if url in urls or any(
            SequenceMatcher(None, title, prior).ratio() >= 0.84 for prior in titles
        ) or any(_same_story(terms, prior) for prior in story_terms):
            continue
        selected.append(candidate)
        urls.add(url)
        titles.append(title)
        story_terms.append(terms)
    return list(selected)


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", "")
    )


def _normalized_title(value: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", value.lower()).split()
    noise = {"the", "a", "an", "and", "to", "of", "in", "on", "for", "with", "update"}
    return " ".join(word for word in words if word not in noise)


def _story_terms(title: str, summary: str) -> set[str]:
    noise = {
        "about", "after", "against", "also", "been", "from", "have", "into", "more",
        "new", "now", "that", "their", "this", "through", "update", "using", "with",
        "security", "vulnerability", "attackers", "threat", "critical",
    }
    terms = set()
    for word in re.findall(r"[a-z0-9]+", f"{title} {summary[:500]}".lower()):
        if len(word) < 4 or word in noise:
            continue
        for suffix in ("ing", "ers", "ed", "es", "s"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 4:
                word = word[: -len(suffix)]
                break
        terms.add(word)
    return terms


def _same_story(left: set[str], right: set[str]) -> bool:
    if not left or not right:
        return False
    shared = left & right
    return len(shared) >= 4 and len(shared) / min(len(left), len(right)) >= 0.42


def write_preview(renderer: ReportRenderer, report: DailyReport, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(renderer.render_html(report), encoding="utf-8")
    return path.resolve()


def open_preview(path: str | Path) -> bool:
    """Open a generated preview in the system's default web browser."""
    return webbrowser.open(Path(path).resolve().as_uri())


def rewrite_report(
    report: DailyReport,
    summarizer: OllamaSummarizer,
    *,
    fallback_on_error: bool = False,
) -> DailyReport:
    """Rewrite display copy without changing persisted source records."""
    rewritten = []
    for item in report.items:
        try:
            brief = summarizer.rewrite_brief(title=item.title, content=item.summary)
        except Exception:
            if fallback_on_error:
                return report
            raise
        rewritten.append(replace(item, title=brief.title, summary=brief.summary))
    return replace(report, items=tuple(rewritten))
