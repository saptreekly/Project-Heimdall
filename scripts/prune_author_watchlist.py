#!/usr/bin/env python3
"""Prune low-yield authors from the scheduled ingest watchlist."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data" / "scheduled_ingest.json"


def main() -> int:
    from heimdall.ingestion.author_watchlist import AuthorWatchlistStore, prune_stale_authors

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--narrative", default="")
    parser.add_argument("--min-polls", type=int, default=2)
    parser.add_argument("--max-inserts-from-polls", type=int, default=0)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    names = [
        job["narrative_name"]
        for job in config.get("jobs", [])
        if job.get("platform", "").lower() == "x"
    ]
    if args.narrative:
        names = [args.narrative]

    store = AuthorWatchlistStore.load()
    total = 0
    for name in names:
        removed = prune_stale_authors(
            name,
            min_polls=args.min_polls,
            max_inserts_from_polls=args.max_inserts_from_polls,
            store=store,
        )
        total += len(removed)
        if removed:
            print(f"{name}: pruned {len(removed)} author(s)")
            for author_id in removed:
                row = store.narrative(name).authors.get(author_id)
                handle = row.handle if row else author_id
                print(f"  - @{handle or author_id}")

    if total == 0:
        print("No authors pruned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
