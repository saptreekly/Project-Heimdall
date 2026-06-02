#!/usr/bin/env python3
"""Track text coordination tier crossings and maintain WATCHLIST.md."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "web" / "public" / "data" / "snapshot.json"
DEFAULT_STATE = ROOT / "data" / "dashboard" / "watchlist_state.json"
DEFAULT_WATCHLIST = ROOT / "data" / "dashboard" / "WATCHLIST.md"

THRESHOLDS = (
    (0.65, "critical"),
    (0.55, "elevated"),
    (0.38, "watch"),
)


def tier_for_score(score: float | None) -> str:
    if score is None:
        return "none"
    for floor, name in THRESHOLDS:
        if score >= floor:
            return name
    return "none"


TIER_RANK = {"none": 0, "watch": 1, "elevated": 2, "critical": 3}


@dataclass(frozen=True)
class TierCrossing:
    narrative: str
    previous_tier: str
    new_tier: str
    score: float
    combined: float | None
    signals: list[str]


def load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def evaluate_crossings(data: dict, state: dict) -> tuple[list[TierCrossing], dict]:
    crossings: list[TierCrossing] = []
    new_state = dict(state)
    now = datetime.now(UTC).isoformat()

    for summary in data.get("narratives") or []:
        name = str(summary.get("name") or summary.get("id"))
        nid = str(summary["id"])
        bundle = (data.get("by_narrative_id") or {}).get(nid, {})
        cib = bundle.get("cib") or {}
        score = cib.get("text_coordination_score")
        if score is None:
            continue
        score_f = float(score)
        new_tier = tier_for_score(score_f)
        prev = state.get(name, {})
        prev_tier = str(prev.get("tier") or "none")

        entry = {
            "text_coordination": round(score_f, 4),
            "combined_suspicion": cib.get("suspicion_score"),
            "tier": new_tier,
            "updated_at": now,
            "snapshot_generated_at": data.get("generated_at"),
        }
        new_state[name] = entry

        if TIER_RANK[new_tier] > TIER_RANK.get(prev_tier, 0):
            text_signals = list(cib.get("text_signals") or cib.get("signals") or [])[:5]
            crossings.append(
                TierCrossing(
                    narrative=name,
                    previous_tier=prev_tier,
                    new_tier=new_tier,
                    score=score_f,
                    combined=float(cib["suspicion_score"]) if cib.get("suspicion_score") is not None else None,
                    signals=text_signals,
                )
            )

    return crossings, new_state


def render_watchlist(data: dict, state: dict) -> str:
    lines = [
        "# Coordination watchlist",
        "",
        "Auto-maintained when `text_coordination_score` crosses **0.38 (watch)**, "
        "**0.55 (elevated)**, or **0.65 (critical)**.",
        "",
        f"_Updated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} · "
        f"snapshot `{data.get('generated_at', '?')}`_",
        "",
        "| Narrative | Tier | Text coord | Combined | Last change |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for summary in data.get("narratives") or []:
        name = str(summary.get("name") or summary.get("id"))
        st = state.get(name, {})
        tier = st.get("tier", "none")
        text = st.get("text_coordination", "—")
        combined = st.get("combined_suspicion", "—")
        updated = st.get("updated_at", "—")
        if isinstance(text, float):
            text = f"{text:.2f}"
        if isinstance(combined, float):
            combined = f"{combined:.2f}"
        lines.append(f"| {name} | **{tier}** | {text} | {combined} | {updated} |")

    lines.extend(["", "## Recent crossings", ""])
    history = state.get("_history") or []
    if not history:
        lines.append("_No tier crossings recorded yet._")
    else:
        for event in history[-20:]:
            lines.append(
                f"- **{event['at']}** · {event['narrative']}: "
                f"{event['from']} → **{event['to']}** (text {event['score']:.2f})"
            )
    lines.append("")
    return "\n".join(lines)


def apply_crossings(state: dict, crossings: list[TierCrossing]) -> dict:
    history = list(state.get("_history") or [])
    now = datetime.now(UTC).isoformat()
    for cross in crossings:
        history.append(
            {
                "at": now,
                "narrative": cross.narrative,
                "from": cross.previous_tier,
                "to": cross.new_tier,
                "score": cross.score,
                "combined": cross.combined,
                "signals": cross.signals,
            }
        )
    state["_history"] = history[-100:]
    return state


def crossings_json(crossings: list[TierCrossing]) -> list[dict]:
    return [
        {
            "narrative": c.narrative,
            "previous_tier": c.previous_tier,
            "new_tier": c.new_tier,
            "score": c.score,
            "combined": c.combined,
            "signals": c.signals,
        }
        for c in crossings
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-s", "--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    parser.add_argument(
        "--crossings-out",
        type=Path,
        help="Write new crossings JSON for workflow issue creation.",
    )
    parser.add_argument("--write", action="store_true", help="Persist state and WATCHLIST.md")
    args = parser.parse_args()

    data = load_snapshot(args.snapshot)
    state = load_state(args.state)
    crossings, new_state = evaluate_crossings(data, state)
    new_state = apply_crossings(new_state, crossings)

    if args.write:
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")
        args.watchlist.write_text(render_watchlist(data, new_state), encoding="utf-8")

    if args.crossings_out:
        args.crossings_out.write_text(json.dumps(crossings_json(crossings), indent=2), encoding="utf-8")

    if crossings:
        for cross in crossings:
            print(
                f"CROSSING {cross.narrative}: {cross.previous_tier} -> {cross.new_tier} "
                f"(text={cross.score:.2f})"
            )
    else:
        print("No new tier crossings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
