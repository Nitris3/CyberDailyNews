"""Known-exploited-vulnerability catalog collector."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
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
    ) -> None:
        if source.kind != "api":
            raise ValueError("KEVCollector requires an API source")
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

