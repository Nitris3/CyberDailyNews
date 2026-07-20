from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from ccip.domain import CollectedItem


def test_collected_item_is_immutable() -> None:
    item = CollectedItem(
        external_id="1",
        source="source",
        title="title",
        url="https://example.com",
        published_at=datetime.now(UTC),
        content="content",
        category="category",
    )

    with pytest.raises(FrozenInstanceError):
        item.title = "changed"  # type: ignore[misc]

