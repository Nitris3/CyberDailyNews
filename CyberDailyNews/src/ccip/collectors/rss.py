"""RSS and Atom feed collector."""

from __future__ import annotations

import calendar
import hashlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from urllib.request import Request, urlopen

import feedparser  # type: ignore[import-untyped]

from ccip.config import SourceConfig
from ccip.domain import CollectedItem

FeedFetcher = Callable[[str, float], bytes]


class FeedCollectionError(RuntimeError):
    """A source could not be fetched or parsed safely."""


def fetch_feed(url: str, timeout_seconds: float) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml",
            "User-Agent": "CCIP/0.1 (+cyber-intelligence-feed-reader)",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return cast(bytes, response.read())


class RSSCollector:
    def __init__(
        self,
        source: SourceConfig,
        *,
        timeout_seconds: float = 20,
        fetcher: FeedFetcher = fetch_feed,
    ) -> None:
        if source.kind != "rss":
            raise ValueError("RSSCollector requires an RSS source")
        self.source = source
        self.timeout_seconds = timeout_seconds
        self.fetcher = fetcher

    @property
    def name(self) -> str:
        return self.source.name

    def collect(self) -> Sequence[CollectedItem]:
        if not self.source.enabled:
            return ()
        try:
            payload = self.fetcher(self.source.url, self.timeout_seconds)
        except Exception as error:
            raise FeedCollectionError(f"failed to fetch {self.source.name}: {error}") from error

        parsed = feedparser.parse(payload)
        if parsed.bozo and not parsed.entries:
            message = f"failed to parse {self.source.name}: {parsed.bozo_exception}"
            raise FeedCollectionError(message)

        seen: set[str] = set()
        items: list[CollectedItem] = []
        for entry in parsed.entries:
            item = self._normalize(entry)
            if item.external_id not in seen:
                seen.add(item.external_id)
                items.append(item)
        return items

    def _normalize(self, entry: Any) -> CollectedItem:
        link = str(entry.get("link", "")).strip()
        title = str(entry.get("title", "Untitled")).strip() or "Untitled"
        content = self._content(entry)
        external_id = str(entry.get("id") or entry.get("guid") or link).strip()
        if not external_id:
            digest_input = f"{self.source.name}\0{title}\0{content}".encode()
            external_id = hashlib.sha256(digest_input).hexdigest()
        return CollectedItem(
            external_id=external_id,
            source=self.source.name,
            title=title,
            url=link or self.source.url,
            published_at=self._published_at(entry),
            content=content,
            category=self.source.category,
            metadata={"priority": self.source.priority, "feed_url": self.source.url},
        )

    @staticmethod
    def _content(entry: Any) -> str:
        content = entry.get("content") or ()
        if content and isinstance(content, list):
            value = content[0].get("value", "")
            if value:
                return str(value).strip()
        return str(entry.get("summary") or entry.get("description") or "").strip()

    @staticmethod
    def _published_at(entry: Any) -> datetime:
        parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed_time:
            return datetime.fromtimestamp(calendar.timegm(parsed_time), tz=UTC)
        return datetime.now(UTC)
