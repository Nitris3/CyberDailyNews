import json
from datetime import UTC, datetime

import pytest

from ccip.collectors.kev import CatalogCollectionError, KEVCollector
from ccip.config import SourceConfig


def source(*, enabled: bool = True) -> SourceConfig:
    return SourceConfig(
        name="Known Exploited Vulnerabilities",
        kind="api",
        url="https://example.com/kev.json",
        category="Exploited Vulnerabilities",
        priority=5,
        enabled=enabled,
    )


def catalog() -> bytes:
    return json.dumps(
        {
            "vulnerabilities": [
                {
                    "cveID": "CVE-2026-1234",
                    "vendorProject": "Example",
                    "product": "Gateway",
                    "vulnerabilityName": "Remote code execution",
                    "dateAdded": "2026-07-20",
                    "shortDescription": "Attackers can execute code.",
                    "requiredAction": "Apply the vendor update.",
                    "dueDate": "2026-07-27",
                    "knownRansomwareCampaignUse": "Known",
                },
                {"missing": "identifier"},
            ]
        }
    ).encode()


def test_kev_collector_normalizes_catalog_records() -> None:
    items = KEVCollector(source(), fetcher=lambda url, timeout: catalog()).collect()

    assert len(items) == 1
    assert items[0].external_id == "CVE-2026-1234"
    assert items[0].published_at == datetime(2026, 7, 20, tzinfo=UTC)
    assert items[0].metadata["known_ransomware_use"] is True
    assert "Apply the vendor update" in items[0].content


def test_kev_collector_rejects_invalid_catalog() -> None:
    collector = KEVCollector(source(), fetcher=lambda url, timeout: b'{"items": []}')

    with pytest.raises(CatalogCollectionError, match="invalid vulnerability catalog"):
        collector.collect()


def test_kev_collector_wraps_transport_or_json_errors() -> None:
    collector = KEVCollector(source(), fetcher=lambda url, timeout: b"not-json")

    with pytest.raises(CatalogCollectionError, match="failed to load"):
        collector.collect()


def test_kev_collector_skips_disabled_source() -> None:
    collector = KEVCollector(
        source(enabled=False),
        fetcher=lambda url, timeout: (_ for _ in ()).throw(AssertionError("fetched")),
    )

    assert collector.collect() == ()
