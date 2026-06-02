#!/usr/bin/env python3
"""Track sentiment trend and week-over-week alert changes from snapshot.json."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "web" / "public" / "data" / "snapshot.json"
DEFAULT_STATE = ROOT / "data" / "dashboard" / "sentiment_watchlist_state.json"
DEFAULT_WATCHLIST = ROOT / "data" / "dashboard" / "SENTIMENT_WATCHLIST.md"

TREND_RANK = {
    "insufficient_data": 0,
    "stable": 1,
    "declining": 2,
    "escalating": 3,
}


@dataclass(frozen=True)
class SentimentAlert:
    narrative: str
    kind: str
    detail: str
    trend: str
    wow_alert: str | None


def load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def evaluate_alerts(data: dict, state: dict) -> tuple[list[SentimentAlert], dict]:
    alerts: list[SentimentAlert] = []
    new_state = dict(state)
    now = datetime.now(UTC).isoformat()

    for summary in data.get("narratives") or []:
        name = str(summary.get("name") or summary.get("id"))
        nid = str(summary["id"])
        bundle = (data.get("by_narrative_id") or {}).get(nid, {})
        sentiment = bundle.get("sentiment") or {}
        trend = str(sentiment.get("trend") or "insufficient_data")
        wow = sentiment.get("week_over_week") or {}
        wow_alert = wow.get("alert") if wow.get("available") else None
        divergence = sentiment.get("divergence_days") or []

        entry = {
            "trend": trend,
            "wow_alert": wow_alert,
            "divergence_days": len(divergence),
            "updated_at": now,
            "snapshot_generated_at": data.get("generated_at"),
        }
        prev = state.get(name, {})
        prev_trend = str(prev.get("trend") or "insufficient_data")
        prev_wow = prev.get("wow_alert")
        new_state[name] = entry

        if TREND_RANK.get(trend, 0) > TREND_RANK.get(prev_trend, 0) and trend == "escalating":
            alerts.append(
                SentimentAlert(
                    narrative=name,
                    kind="trend_escalating",
                    detail=f"Sentiment trend crossed to escalating (was {prev_trend})",
                    trend=trend,
                    wow_alert=wow_alert,
                )
            )

        if wow_alert and wow_alert != prev_wow:
            alerts.append(
                SentimentAlert(
                    narrative=name,
                    kind=str(wow_alert),
                    detail=f"Week-over-week alert: {wow_alert.replace('_', ' ')}",
                    trend=trend,
                    wow_alert=str(wow_alert),
                )
            )

        if divergence and int(prev.get("divergence_days") or 0) < len(divergence):
            spike = divergence[0]
            alerts.append(
                SentimentAlert(
                    narrative=name,
                    kind="volume_outrage_divergence",
                    detail=(
                        f"{spike.get('date')}: {spike.get('count')} posts, "
                        f"mean outrage {float(spike.get('mean_outrage', 0)):.3f}"
                    ),
                    trend=trend,
                    wow_alert=wow_alert,
                )
            )

    return alerts, new_state


def render_watchlist(data: dict, state: dict, alerts: list[SentimentAlert]) -> str:
    generated = data.get("generated_at") or "unknown"
    lines = [
        "# Sentiment watchlist",
        "",
        f"_Updated from snapshot generated at {generated}_",
        "",
        "## Current narrative status",
        "",
        "| Narrative | Trend | WoW alert | Divergence days |",
        "| --- | --- | --- | ---: |",
    ]
    for summary in data.get("narratives") or []:
        name = str(summary.get("name") or summary.get("id"))
        entry = state.get(name, {})
        lines.append(
            f"| {name} | {entry.get('trend', '—')} | {entry.get('wow_alert') or '—'} | "
            f"{entry.get('divergence_days', 0)} |"
        )

    lines.extend(["", "## Recent alerts", ""])
    if not alerts:
        lines.append("_No new sentiment alerts this run._")
    else:
        for alert in alerts:
            lines.append(f"- **{alert.narrative}** — {alert.kind}: {alert.detail}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-s", "--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--crossings-out",
        type=Path,
        help="Write alert JSON for GitHub issue automation.",
    )
    args = parser.parse_args()

    if not args.snapshot.is_file():
        print(f"Missing snapshot: {args.snapshot}", file=__import__("sys").stderr)
        return 1

    data = load_snapshot(args.snapshot)
    state = load_state(args.state)
    alerts, new_state = evaluate_alerts(data, state)

    if args.crossings_out:
        args.crossings_out.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "narrative": a.narrative,
                "kind": a.kind,
                "detail": a.detail,
                "trend": a.trend,
                "wow_alert": a.wow_alert,
            }
            for a in alerts
        ]
        args.crossings_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.write:
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")
        args.watchlist.write_text(render_watchlist(data, new_state, alerts), encoding="utf-8")

    print(json.dumps({"alert_count": len(alerts), "alerts": [a.__dict__ for a in alerts]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
