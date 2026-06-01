#!/usr/bin/env python3
"""Copy ingested heimdall.db into the repo and export snapshot.json for GitHub Pages."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DB = ROOT / "heimdall.db"
TARGET_DB = ROOT / "data" / "dashboard" / "heimdall.db"
SNAPSHOT = ROOT / "web" / "public" / "data" / "snapshot.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=SOURCE_DB,
        help=f"SQLite file to publish (default: {SOURCE_DB})",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"Missing database: {args.source}", file=sys.stderr)
        print("Run ingest first, e.g. POST /api/v1/ingest", file=sys.stderr)
        return 1

    TARGET_DB.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.source, TARGET_DB)
    print(f"Copied → {TARGET_DB.relative_to(ROOT)} ({TARGET_DB.stat().st_size // 1024} KB)")

    env = {**__import__("os").environ, "DATABASE_URL": f"sqlite+aiosqlite:///{TARGET_DB.resolve()}"}
    subprocess.run(
        [sys.executable, "scripts/export_dashboard_data.py"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    print(f"Exported → {SNAPSHOT.relative_to(ROOT)}")
    print()
    print("Commit and push:")
    print("  git add data/dashboard/heimdall.db web/public/data/snapshot.json")
    print('  git commit -m "chore: publish ingest data for dashboard"')
    print("  git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
