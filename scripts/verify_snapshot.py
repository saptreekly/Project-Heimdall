#!/usr/bin/env python3
"""Fail CI when dashboard snapshot export is missing or empty."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "web" / "public" / "data" / "snapshot.json"
PREVIOUS = ROOT / "data" / "dashboard" / ".snapshot_smoke_previous.json"


def main() -> int:
    if not SNAPSHOT.is_file():
        print(f"Missing {SNAPSHOT}", file=sys.stderr)
        return 1

    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    generated = data.get("generated_at")
    if not generated:
        print("snapshot.json missing generated_at", file=sys.stderr)
        return 1

    narratives = data.get("narratives") or []
    if not narratives:
        print("snapshot.json has no narratives", file=sys.stderr)
        return 1

    total_posts = 0
    for summary in narratives:
        nid = str(summary["id"])
        bundle = data.get("by_narrative_id", {}).get(nid, {})
        total_posts += len(bundle.get("posts") or [])

    if total_posts < 1:
        print("snapshot.json has zero posts across narratives", file=sys.stderr)
        return 1

    print(f"OK: {len(narratives)} narrative(s), {total_posts} posts, generated_at={generated}")

    if PREVIOUS.is_file():
        try:
            prev = json.loads(PREVIOUS.read_text(encoding="utf-8"))
            prev_at = prev.get("generated_at")
            if prev_at and generated <= prev_at:
                print(
                    f"Warning: generated_at did not advance ({prev_at} -> {generated})",
                    file=sys.stderr,
                )
        except json.JSONDecodeError:
            pass

    PREVIOUS.parent.mkdir(parents=True, exist_ok=True)
    PREVIOUS.write_text(
        json.dumps({"generated_at": generated, "checked_at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
