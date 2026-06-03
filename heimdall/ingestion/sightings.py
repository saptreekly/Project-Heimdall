"""Append-only log of ingest sightings for coordination timeline analysis."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_SIGHTINGS_PATH = Path("data/dashboard/ingest_sightings.jsonl")


def sightings_path() -> Path:
    override = os.environ.get("INGEST_SIGHTINGS_PATH", "").strip()
    if override:
        return Path(override)
    return DEFAULT_SIGHTINGS_PATH


def append_ingest_sighting(record: dict, *, path: Path | None = None) -> None:
    target = path or sightings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"at": datetime.now(UTC).isoformat(), **record}
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")


def load_sightings_for_narrative(narrative_name: str, *, path: Path | None = None) -> list[dict]:
    target = path or sightings_path()
    if not target.is_file():
        return []
    rows: list[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("narrative_name") == narrative_name:
            rows.append(row)
    return rows


def summarize_sightings(rows: list[dict]) -> dict:
    daily_resightings: dict[str, int] = {}
    daily_net_new: dict[str, int] = {}
    for row in rows:
        day = str(row.get("at", ""))[:10]
        if not day:
            continue
        event = row.get("event", "duplicate")
        if event == "inserted":
            daily_net_new[day] = daily_net_new.get(day, 0) + 1
        elif event in ("duplicate", "updated"):
            daily_resightings[day] = daily_resightings.get(day, 0) + 1
    return {
        "total_resightings": sum(daily_resightings.values()),
        "total_net_new": sum(daily_net_new.values()),
        "daily_resightings": daily_resightings,
        "daily_net_new": daily_net_new,
    }
