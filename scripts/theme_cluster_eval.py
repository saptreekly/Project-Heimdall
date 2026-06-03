#!/usr/bin/env python3
"""Evaluate theme clustering quality on synthetic or snapshot narratives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SYNTHETIC_NARRATIVE = [
    (1, "red wave heat preparedness cross seminar", "a1"),
    (2, "red wave heat cross training seminar", "a2"),
    (3, "red wave preparedness heat wave", "a3"),
    (4, "election fraud midterm trump vote need accountability", "b1"),
    (5, "election midterm fraud trump vote accountability issue", "b2"),
    (6, "election fraud vote midterm trump federal order", "b3"),
    (7, "vix mkt ndx btc spx call puts", "c1"),
    (8, "btc eth spy qqq vix mkt ndx", "c2"),
    (9, "spx ndx vix mkt btc eth sol", "c3"),
]


def run_synthetic_eval() -> dict:
    from heimdall.nlp.theme_clusters import cluster_posts, report_to_dict

    report = cluster_posts(
        SYNTHETIC_NARRATIVE,
        narrative_id=0,
        narrative_keywords=["election", "fraud", "red wave", "midterm"],
    )
    data = report_to_dict(report)
    political = [c for c in data["clusters"] if not c.get("filter_reason") and not c.get("is_market_chatter")]
    market = [c for c in data["clusters"] if c.get("is_market_chatter") or c.get("filter_reason") == "market"]
    return {
        "method": data["method"],
        "model": data["model"],
        "narrative_clusters": len(political),
        "market_or_filtered_clusters": len(market),
        "quality_metrics": data.get("quality_metrics", {}),
        "emerging_theme_count": data.get("emerging_theme_count", 0),
        "passed": len(political) >= 2 and len(market) >= 1,
    }


def run_snapshot_eval(snapshot_path: Path) -> dict:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    summaries = []
    for narrative in payload.get("narratives", []):
        bundle = payload.get("by_narrative_id", {}).get(str(narrative["id"]), {})
        themes = bundle.get("themes") or {}
        if not themes.get("available"):
            continue
        summaries.append(
            {
                "narrative": narrative.get("name"),
                "method": themes.get("method"),
                "model": themes.get("model"),
                "cluster_count": themes.get("cluster_count"),
                "distinct_theme_count": themes.get("distinct_theme_count"),
                "quality_metrics": themes.get("quality_metrics"),
                "filtered_post_count": themes.get("filtered_post_count"),
            }
        )
    return {"narratives": summaries}


def main() -> None:
    parser = argparse.ArgumentParser(description="Theme clustering evaluation harness")
    parser.add_argument("--synthetic", action="store_true", help="Run planted-frame synthetic eval")
    parser.add_argument("--snapshot", type=Path, help="Evaluate themes section of snapshot.json")
    args = parser.parse_args()

    if args.synthetic:
        result = run_synthetic_eval()
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result.get("passed") else 1)

    if args.snapshot:
        result = run_snapshot_eval(args.snapshot)
        print(json.dumps(result, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
