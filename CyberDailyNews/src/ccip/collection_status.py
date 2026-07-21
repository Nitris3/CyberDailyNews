"""Persistent, non-sensitive collection health snapshots for the dashboard."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ccip.pipeline import IngestionResult

STATUS_PATH = Path("data/collection.status.json")


def write_collection_status(result: IngestionResult, path: Path = STATUS_PATH) -> None:
    document = {
        "completed_at": datetime.now().astimezone().isoformat(),
        "stored": result.stored,
        "collected": result.collected,
        "skipped": result.skipped,
        "collection_seconds": result.collection_seconds,
        "processing_seconds": result.processing_seconds,
        "total_seconds": result.total_seconds,
        "rescore_seconds": None,
        "sources": [
            {
                "name": source.source,
                "status": source.status.value,
                "item_count": source.item_count,
                "error": source.error,
            }
            for source in result.sources
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
    temporary.replace(path)


def record_rescore_seconds(seconds: float, path: Path = STATUS_PATH) -> None:
    document = load_collection_status(path)
    if document is None:
        return
    document["rescore_seconds"] = round(seconds, 2)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def load_collection_status(path: Path = STATUS_PATH) -> dict[str, Any] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None
