#!/usr/bin/env python3
"""Dashboard snapshot metrics for CI summaries and health checks."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "web" / "public" / "data" / "snapshot.json"
DEFAULT_HISTORY = ROOT / "data" / "dashboard" / "metrics_history.jsonl"


def load_snapshot(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(data: dict) -> dict:
    narratives = data.get("narratives") or []
    by_id = data.get("by_narrative_id") or {}
    rows: list[dict] = []
    total_posts = 0

    for summary in narratives:
        nid = str(summary["id"])
        bundle = by_id.get(nid, {})
        posts = bundle.get("posts") or []
        cib = bundle.get("cib") or {}
        themes = bundle.get("themes") or {}
        provenance = bundle.get("provenance") or {}
        total_posts += len(posts)
        rows.append(
            {
                "id": summary["id"],
                "name": summary.get("name"),
                "posts_in_snapshot": len(posts),
                "posts_total_db": provenance.get("posts_total_db") or summary.get("post_count"),
                "text_coordination": cib.get("text_coordination_score"),
                "graph_suspicion": cib.get("graph_suspicion_score"),
                "combined_suspicion": cib.get("suspicion_score"),
                "graph_sufficient": cib.get("graph_sufficient"),
                "distinct_themes": themes.get("distinct_theme_count"),
                "emerging_themes": themes.get("emerging_theme_count"),
                "fuzzy_clusters": provenance.get("fuzzy_cluster_count"),
                "duplicate_clusters": provenance.get("duplicate_cluster_count"),
            }
        )

    generated_at = data.get("generated_at")
    age_hours: float | None = None
    if generated_at:
        try:
            ts = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
            age_hours = round((datetime.now(UTC) - ts.astimezone(UTC)).total_seconds() / 3600, 1)
        except ValueError:
            age_hours = None

    return {
        "version": data.get("version"),
        "generated_at": generated_at,
        "age_hours": age_hours,
        "narrative_count": len(narratives),
        "total_posts_in_snapshot": total_posts,
        "cross_pollination_actors": (data.get("cross_pollination") or {}).get("actor_count"),
        "narratives": rows,
    }


def markdown_report(report: dict) -> str:
    lines = [
        "### Dashboard snapshot",
        "",
        f"- **Version:** {report.get('version', '?')}",
        f"- **Generated:** {report.get('generated_at', '?')}"
        + (f" ({report.get('age_hours')}h ago)" if report.get("age_hours") is not None else ""),
        f"- **Narratives:** {report.get('narrative_count', 0)}",
        f"- **Posts in snapshot:** {report.get('total_posts_in_snapshot', 0)}",
    ]
    if report.get("cross_pollination_actors") is not None:
        lines.append(f"- **Cross-pollination actors:** {report['cross_pollination_actors']}")
    lines.extend(["", "| Narrative | Posts | Text coord | Themes | Signals |", "| --- | ---: | ---: | ---: | --- |"])
    for row in report.get("narratives") or []:
        posts = row.get("posts_in_snapshot", "?")
        total = row.get("posts_total_db")
        post_cell = f"{posts}/{total}" if total and total != posts else str(posts)
        text = row.get("text_coordination")
        text_cell = f"{text:.2f}" if isinstance(text, (int, float)) else "—"
        themes = row.get("distinct_themes")
        emerging = row.get("emerging_themes")
        theme_cell = (
            f"{themes} distinct ({emerging} emerging)"
            if themes is not None
            else "—"
        )
        fuzzy = row.get("fuzzy_clusters") or 0
        dup = row.get("duplicate_clusters") or 0
        lines.append(
            f"| {row.get('name', '?')} | {post_cell} | {text_cell} | {theme_cell} | {fuzzy} fuzzy · {dup} dup |"
        )
    return "\n".join(lines) + "\n"


def append_metrics_history(report: dict, path: Path = DEFAULT_HISTORY) -> None:
    """Append one JSON line per UTC day (replaces same-day entry if re-run)."""
    record = {**report, "recorded_at": datetime.now(UTC).isoformat()}
    today = record["recorded_at"][:10]
    existing: list[dict] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("recorded_at", ""))[:10] != today:
                existing.append(row)
    existing.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in existing) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-s", "--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument(
        "--format",
        choices=("json", "markdown", "github-summary"),
        default="markdown",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=None,
        help="Exit 1 if generated_at is older than this many hours (health checks).",
    )
    parser.add_argument(
        "--append-history",
        type=Path,
        nargs="?",
        const=DEFAULT_HISTORY,
        help="Append report JSON to metrics_history.jsonl (one line per UTC day).",
    )
    parser.add_argument(
        "--write-json",
        type=Path,
        help="Write report JSON to this path (for workflow artifacts).",
    )
    args = parser.parse_args()

    try:
        data = load_snapshot(args.snapshot)
    except FileNotFoundError:
        print(f"Missing snapshot: {args.snapshot}", file=sys.stderr)
        return 1

    report = build_report(data)
    if args.max_age_hours is not None and report.get("age_hours") is not None:
        if report["age_hours"] > args.max_age_hours:
            print(
                f"Snapshot stale: {report['age_hours']}h old (max {args.max_age_hours}h)",
                file=sys.stderr,
            )
            return 1

    if args.format == "json":
        print(json.dumps(report, indent=2))
    elif args.format == "github-summary":
        summary_path = Path(__import__("os").environ.get("GITHUB_STEP_SUMMARY", ""))
        if summary_path:
            Path(summary_path).write_text(markdown_report(report), encoding="utf-8")
        else:
            print(markdown_report(report))
    else:
        print(markdown_report(report))

    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.append_history is not None:
        append_metrics_history(report, args.append_history)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
