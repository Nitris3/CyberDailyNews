from datetime import UTC, datetime

import pytest

from ccip.collection import CollectionRunner, HealthStatus
from ccip.collectors.rss import FeedCollectionError, RSSCollector
from ccip.config import SourceConfig

VALID_FEED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Security Feed</title>
<item><guid>item-1</guid><title>Critical issue</title>
<link>https://example.com/1</link><description>Apply the update.</description>
<pubDate>Mon, 20 Jul 2026 12:00:00 GMT</pubDate></item>
<item><guid>item-1</guid><title>Duplicate issue</title>
<link>https://example.com/duplicate</link></item>
</channel></rss>"""


def source(*, enabled: bool = True) -> SourceConfig:
    return SourceConfig(
        name="Example Feed",
        kind="rss",
        url="https://example.com/feed.xml",
        category="Threat Intelligence",
        priority=5,
        enabled=enabled,
    )


def test_rss_collector_normalizes_and_deduplicates_entries() -> None:
    collector = RSSCollector(source(), fetcher=lambda url, timeout: VALID_FEED)

    items = collector.collect()

    assert len(items) == 1
    assert items[0].external_id == "item-1"
    assert items[0].published_at == datetime(2026, 7, 20, 12, tzinfo=UTC)
    assert items[0].metadata["priority"] == 5


def test_rss_collector_skips_disabled_source_without_fetching() -> None:
    def unexpected_fetch(url: str, timeout: float) -> bytes:
        raise AssertionError("disabled source was fetched")

    assert RSSCollector(source(enabled=False), fetcher=unexpected_fetch).collect() == ()


def test_rss_collector_wraps_transport_failure() -> None:
    def failed_fetch(url: str, timeout: float) -> bytes:
        raise TimeoutError("timed out")

    with pytest.raises(FeedCollectionError, match="timed out"):
        RSSCollector(source(), fetcher=failed_fetch).collect()


def test_rss_collector_rejects_malformed_feed() -> None:
    collector = RSSCollector(source(), fetcher=lambda url, timeout: b"not xml")

    with pytest.raises(FeedCollectionError, match="failed to parse"):
        collector.collect()


def test_collection_runner_isolates_failure_and_reports_health() -> None:
    good = RSSCollector(source(), fetcher=lambda url, timeout: VALID_FEED)
    bad_source = source().model_copy(update={"name": "Broken Feed", "url": "https://bad"})
    bad = RSSCollector(
        bad_source,
        fetcher=lambda url, timeout: (_ for _ in ()).throw(TimeoutError("offline")),
    )

    result = CollectionRunner((bad, good)).run()

    assert len(result.items) == 1
    assert [health.status for health in result.sources] == [
        HealthStatus.FAILED,
        HealthStatus.HEALTHY,
    ]


def test_collection_runner_retries_transient_failure_without_delay() -> None:
    attempts = 0

    def flaky_fetch(url: str, timeout: float) -> bytes:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("temporary")
        return VALID_FEED

    result = CollectionRunner(
        (RSSCollector(source(), fetcher=flaky_fetch),),
        retry_attempts=1,
        retry_backoff_seconds=0,
    ).run()

    assert attempts == 2
    assert result.sources[0].status == HealthStatus.HEALTHY


def test_collection_runner_marks_old_feed_as_stale() -> None:
    old_feed = VALID_FEED.replace(b"20 Jul 2026", b"20 Jul 2020")
    collector = RSSCollector(source(), fetcher=lambda url, timeout: old_feed)

    result = CollectionRunner((collector,), stale_after_days=14).run()

    assert result.sources[0].status == HealthStatus.STALE
