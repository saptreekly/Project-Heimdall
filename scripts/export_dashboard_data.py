#!/usr/bin/env python3
"""Export analysis JSON for the GitHub Pages dashboard (web/public/data/snapshot.json)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "web" / "public" / "data" / "snapshot.json"


async def run(out: Path) -> int:
    import os

    from heimdall.db.session import get_session_factory, init_db
    from heimdall.export.dashboard_snapshot import build_dashboard_snapshot

    if os.environ.get("RESCORE_BEFORE_EXPORT", "true").lower() not in ("0", "false", "no"):
        import subprocess

        rescore_env = {
            **os.environ,
            "RESCORE_USE_EMBEDDINGS": os.environ.get("RESCORE_USE_EMBEDDINGS", "false"),
        }
        subprocess.run(
            [sys.executable, "scripts/rescore_dashboard_narratives.py", "--if-stale"],
            cwd=ROOT,
            check=True,
            env=rescore_env,
        )

    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        snapshot = await build_dashboard_snapshot(db)

    if not snapshot["narratives"]:
        print("No narratives in database; run ingest or scripts/seed_dashboard_if_empty.py", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(snapshot['narratives'])} narratives)")

    from heimdall.export.brief import write_brief_artifacts

    brief_dirs = [
        ROOT / "data" / "dashboard" / "briefs",
        ROOT / "web" / "public" / "data" / "briefs",
    ]
    for brief_dir in brief_dirs:
        paths = write_brief_artifacts(snapshot, brief_dir)
        print(f"Wrote {len(paths)} brief artifact(s) to {brief_dir}")

    metrics_src = ROOT / "data" / "dashboard" / "metrics_history.jsonl"
    metrics_dst = ROOT / "web" / "public" / "data" / "metrics_history.jsonl"
    if metrics_src.is_file():
        metrics_dst.parent.mkdir(parents=True, exist_ok=True)
        metrics_dst.write_text(metrics_src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Copied metrics history to {metrics_dst}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.output)))


if __name__ == "__main__":
    main()
