#!/usr/bin/env python3
"""Validate GitHub Actions automation wiring (scripts, schedules, chain)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    expected = {
        "ingest.yml": {"schedule", "workflow_dispatch"},
        "pages.yml": {"schedule", "workflow_run", "workflow_dispatch", "push"},
        "ci.yml": {"push", "pull_request"},
        "maintenance.yml": {"schedule", "workflow_dispatch"},
        "daily-analytics.yml": {"schedule", "workflow_dispatch"},
        "health.yml": {"schedule", "workflow_dispatch"},
        "export.yml": {"workflow_dispatch"},
    }

    script_refs: set[str] = set()
    for wf in WORKFLOWS.glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        if wf.name not in expected:
            warnings.append(f"Unexpected workflow file: {wf.name}")
            continue
        for trigger in expected[wf.name]:
            if f"{trigger}:" not in text:
                errors.append(f"{wf.name}: missing trigger `{trigger}`")
        for match in re.finditer(r"python scripts/(\w+)\.py", text):
            script_refs.add(match.group(1))

    for name in sorted(script_refs):
        path = ROOT / "scripts" / f"{name}.py"
        if not path.is_file():
            errors.append(f"Workflow references missing script: scripts/{name}.py")

    required_scripts = {
        "scheduled_ingest",
        "verify_snapshot",
        "snapshot_report",
        "export_dashboard_data",
        "maintain_dashboard_db",
        "theme_drift_report",
        "keyword_audit",
        "rotate_keywords",
        "coordination_watchlist",
    }
    for name in sorted(required_scripts):
        if not (ROOT / "scripts" / f"{name}.py").is_file():
            errors.append(f"Missing required script: scripts/{name}.py")

    ingest = (WORKFLOWS / "ingest.yml").read_text(encoding="utf-8") if (WORKFLOWS / "ingest.yml").is_file() else ""
    if "workflows: [ingest]" not in (WORKFLOWS / "pages.yml").read_text(encoding="utf-8"):
        errors.append("pages.yml does not chain from ingest via workflow_run")

    if "append_ingest_run" not in (ROOT / "scripts" / "scheduled_ingest.py").read_text(encoding="utf-8"):
        errors.append("scheduled_ingest.py does not log runs to ingest_runs.jsonl")

    if "rotate_keywords.py" not in (WORKFLOWS / "maintenance.yml").read_text(encoding="utf-8"):
        errors.append("maintenance.yml does not run rotate_keywords.py")

    cron_count = len(re.findall(r"cron:", ingest))
    if cron_count < 5:
        warnings.append(f"ingest.yml has {cron_count} cron entries (expected ~5 for 30 runs/day)")

    if errors:
        print("AUTOMATION CHECK FAILED")
        for err in errors:
            print(f"  ERROR: {err}")
        for warn in warnings:
            print(f"  WARN: {warn}")
        return 1

    print("AUTOMATION CHECK OK")
    print(f"  Workflows: {len(list(WORKFLOWS.glob('*.yml')))}")
    print(f"  Script refs: {len(script_refs)}")
    for warn in warnings:
        print(f"  WARN: {warn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
