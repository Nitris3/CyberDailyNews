"""Known-exploited-vulnerability catalog collector."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import time
from typing import Any

from ccip.collectors.rss import fetch_feed
from ccip.config import SourceConfig
from ccip.domain import CollectedItem

CatalogFetcher = Callable[[str, float], bytes]


class CatalogCollectionError(RuntimeError):
    """The vulnerability catalog could not be fetched or validated."""


class KEVCollector:
    def __init__(
        self,
        source: SourceConfig,
        *,
        timeout_seconds: float = 20,
        fetcher: CatalogFetcher = fetch_feed,
        cache_path: Path | None = None,
        cache_hours: float = 0,
    ) -> None:
        if source.kind != "api":
            raise ValueError("KEVCollector requires an API source")
        self.source = source
        self.timeout_seconds = timeout_seconds
        self.fetcher = fetcher
        self.cache_path = cache_path
        self.cache_seconds = cache_hours * 3600

    @property
    def name(self) -> str:
        return self.source.name

    def collect(self) -> Sequence[CollectedItem]:
        if not self.source.enabled:
            return ()
        try:
            payload = self._payload()
            document = json.loads(payload)
        except Exception as error:
            raise CatalogCollectionError(f"failed to load {self.source.name}: {error}") from error
        if not isinstance(document, dict) or not isinstance(document.get("vulnerabilities"), list):
            raise CatalogCollectionError(f"invalid vulnerability catalog: {self.source.name}")

        items: list[CollectedItem] = []
        for record in document["vulnerabilities"]:
            if not isinstance(record, dict):
                continue
            item = self._normalize(record)
            if item is not None:
                items.append(item)
        return items

    def _payload(self) -> bytes:
        cache = self.cache_path
        if (
            cache is not None
            and self.cache_seconds > 0
            and cache.exists()
            and time() - cache.stat().st_mtime < self.cache_seconds
        ):
            return cache.read_bytes()
        payload = self.fetcher(self.source.url, self.timeout_seconds)
        document = json.loads(payload)
        if not isinstance(document, dict) or not isinstance(document.get("vulnerabilities"), list):
            raise ValueError("invalid vulnerability catalog")
        if cache is not None and self.cache_seconds > 0:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(payload)
        return payload

    def _normalize(self, record: dict[str, Any]) -> CollectedItem | None:
        cve_id = str(record.get("cveID", "")).strip().upper()
        if not cve_id:
            return None
        vendor = str(record.get("vendorProject", "Unknown vendor")).strip()
        product = str(record.get("product", "Unknown product")).strip()
        name = str(record.get("vulnerabilityName", cve_id)).strip()
        description = str(record.get("shortDescription", "")).strip()
        action = str(record.get("requiredAction", "")).strip()
        content = " ".join(part for part in (description, action) if part)
        return CollectedItem(
            external_id=cve_id,
            source=self.source.name,
            title=f"{cve_id}: {name}",
            url=f"https://www.cve.org/CVERecord?id={cve_id}",
            published_at=self._date_added(record.get("dateAdded")),
            content=content,
            category=self.source.category,
            metadata={
                "priority": self.source.priority,
                "vendor": vendor,
                "product": product,
                "due_date": record.get("dueDate"),
                "known_ransomware_use": record.get("knownRansomwareCampaignUse") == "Known",
            },
        )

    @staticmethod
    def _date_added(value: object) -> datetime:
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                pass
        return datetime.now(UTC)
