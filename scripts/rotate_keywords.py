#!/usr/bin/env python3
"""Auto-swap stale X ingest keywords for high-scoring gap suggestions."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from scripts.keyword_audit import (
    DEFAULT_CONFIG,
    DEFAULT_DB,
    DEFAULT_RUNS,
    DEFAULT_SNAPSHOT,
    KeywordAuditReport,
    KeywordStats,
    SuggestedKeyword,
    build_report,
    load_ingest_runs,
    _recent_post_texts,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROTATION_STATE = ROOT / "data" / "dashboard" / "x_keyword_rotation.json"
DEFAULT_LOG = ROOT / "data" / "dashboard" / "keyword_rotation_log.jsonl"

MIN_KEYWORDS = 3
MAX_KEYWORDS = 8
MIN_RUNS_BEFORE_SWAP = 5
MIN_RUNS_STALE = 3
STALE_MAX_INSERTED = 2
STALE_MAX_YIELD = 0.15
DEFAULT_PINNED = ("2026 midterms",)


@dataclass
class RotationPlan:
    narrative: str
    before: list[str]
    after: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    pinned: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.before != self.after


DEFAULT_PINNED = ("2026 midterms",)
_YEAR_TOKENS = frozenset({"2024", "2025", "2026", "2027"})


def _semantic_tokens(text: str) -> set[str]:
    return {t for t in text.lower().split() if t not in _YEAR_TOKENS and len(t) >= 3}


def _too_similar_to_existing(query: str, keywords: list[str]) -> bool:
    q = query.lower().strip()
    q_sem = _semantic_tokens(q)
    for kw in keywords:
        k = kw.lower().strip()
        if q == k:
            return True
        if q in k or k in q:
            return True
        k_sem = _semantic_tokens(k)
        if not q_sem or not k_sem:
            continue
        if q_sem <= k_sem or k_sem <= q_sem:
            return True
        union = q_sem | k_sem
        overlap = len(q_sem & k_sem) / len(union)
        if overlap >= 0.66:
            return True
    return False


def identify_stale(
    stats: list[KeywordStats],
    *,
    pinned: set[str],
    current_keywords: list[str],
    min_keywords: int,
) -> list[str]:
    """Keywords to remove, worst yield first, respecting pins and floor."""
    candidates: list[tuple[str, str]] = []

    for stat in stats:
        if stat.keyword not in current_keywords or stat.keyword in pinned:
            continue
        if stat.runs >= MIN_RUNS_STALE and stat.inserted == 0 and stat.fetched == 0:
            candidates.append((stat.keyword, "dead (0 fetched/inserted)"))
        elif (
            stat.runs >= MIN_RUNS_STALE
            and stat.inserted <= STALE_MAX_INSERTED
            and stat.yield_rate <= STALE_MAX_YIELD
        ):
            candidates.append((stat.keyword, f"low yield ({stat.yield_rate:.2f} ins/run)"))

    candidates.sort(
        key=lambda item: next(
            (s.yield_rate for s in stats if s.keyword == item[0]),
            0.0,
        )
    )

    removable: list[str] = []
    reasons: dict[str, str] = {}
    for kw, reason in candidates:
        if len(current_keywords) - len(removable) <= min_keywords:
            break
        if kw not in removable:
            removable.append(kw)
            reasons[kw] = reason
    return removable


def pick_additions(
    suggestions: list[SuggestedKeyword],
    *,
    current_after_removals: list[str],
    max_keywords: int,
) -> list[str]:
    slots = max(0, max_keywords - len(current_after_removals))
    if slots <= 0:
        return []

    added: list[str] = []
    for sug in suggestions:
        query = sug.query.strip()
        if not query or len(query) < 4:
            continue
        if _too_similar_to_existing(query, current_after_removals + added):
            continue
        added.append(query)
        if len(added) >= slots:
            break
    return added


def build_rotation_plan(
    report: KeywordAuditReport,
    *,
    narrative: str,
    current_keywords: list[str],
    pinned: tuple[str, ...],
    min_keywords: int,
    max_keywords: int,
    min_runs_before_swap: int,
    ingest_run_count: int,
) -> RotationPlan:
    pinned_set = {p.lower() for p in pinned}
    pinned_present = [k for k in current_keywords if k.lower() in pinned_set]

    plan = RotationPlan(
        narrative=narrative,
        before=list(current_keywords),
        pinned=pinned_present,
    )

    if ingest_run_count < min_runs_before_swap:
        plan.after = list(current_keywords)
        plan.notes.append(
            f"Skipped rotation: only {ingest_run_count} ingest run(s) in window "
            f"(need {min_runs_before_swap})."
        )
        return plan

    removed = identify_stale(
        report.stats,
        pinned=set(pinned_present),
        current_keywords=current_keywords,
        min_keywords=min_keywords,
    )
    interim = [k for k in current_keywords if k not in removed]
    added = pick_additions(
        report.suggestions,
        current_after_removals=interim,
        max_keywords=max_keywords,
    )

    if not removed and not added:
        plan.after = list(current_keywords)
        plan.notes.append("No stale keywords to remove and no new suggestions to add.")
        return plan

    # 1:1 swap when possible — each removal makes room for one addition
    if len(added) > len(removed) and len(interim) + len(added) > max_keywords:
        added = added[: max(len(removed), max_keywords - len(interim))]

    after = interim + added
    if len(after) > max_keywords:
        after = after[:max_keywords]

    plan.removed = removed
    plan.added = added
    plan.after = after
    if removed:
        plan.notes.append(f"Removed {len(removed)} stale keyword(s).")
    if added:
        plan.notes.append(f"Added {len(added)} suggested keyword(s).")
    return plan


def load_scheduled_keywords(config_path: Path, narrative: str) -> list[str]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for job in config.get("jobs") or []:
        if job.get("narrative_name") == narrative:
            return list(job.get("keywords") or [])
    raise SystemExit(f"Narrative {narrative!r} not found in {config_path}")


def write_scheduled_keywords(config_path: Path, narrative: str, keywords: list[str]) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    updated = False
    for job in config.get("jobs") or []:
        if job.get("narrative_name") == narrative:
            job["keywords"] = keywords
            updated = True
            break
    if not updated:
        raise SystemExit(f"Narrative {narrative!r} not found in {config_path}")
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def _keywords_fingerprint(keywords: list[str]) -> str:
    payload = json.dumps(sorted(k.strip().lower() for k in keywords))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def reset_rotation_state(path: Path, keywords: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "keyword_index": 0,
                "keywords_fingerprint": _keywords_fingerprint(keywords),
                "rotated_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def append_rotation_log(plan: RotationPlan, path: Path = DEFAULT_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "at": datetime.now(UTC).isoformat(),
        "narrative": plan.narrative,
        "before": plan.before,
        "after": plan.after,
        "removed": plan.removed,
        "added": plan.added,
        "pinned": plan.pinned,
        "notes": plan.notes,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def markdown_plan(plan: RotationPlan) -> str:
    lines = [
        "### Keyword rotation",
        "",
        f"- **Narrative:** {plan.narrative}",
        f"- **Changed:** {'yes' if plan.changed else 'no'}",
    ]
    if plan.pinned:
        lines.append(f"- **Pinned:** {', '.join(f'`{p}`' for p in plan.pinned)}")
    if plan.removed:
        lines.append(f"- **Removed:** {', '.join(f'`{k}`' for k in plan.removed)}")
    if plan.added:
        lines.append(f"- **Added:** {', '.join(f'`{k}`' for k in plan.added)}")
    lines.extend(["", "**Keywords now:**", ""])
    for kw in plan.after:
        lines.append(f"- `{kw}`")
    if plan.notes:
        lines.extend(["", "**Notes:**", ""])
        lines.extend(f"- {n}" for n in plan.notes)
    lines.append("")
    return "\n".join(lines)


async def plan_rotation(args: argparse.Namespace) -> RotationPlan:
    import os

    if args.db.is_file():
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{args.db.resolve()}"

    post_texts = await _recent_post_texts(args.narrative, limit=args.post_limit)
    runs = load_ingest_runs(args.runs, days=args.days)
    report = build_report(
        config_path=args.config,
        runs_path=args.runs,
        snapshot_path=args.snapshot,
        narrative_name=args.narrative,
        window_days=args.days,
        post_texts=post_texts,
    )
    current = load_scheduled_keywords(args.config, args.narrative)
    pinned = tuple(args.pin) if args.pin else DEFAULT_PINNED

    return build_rotation_plan(
        report,
        narrative=args.narrative,
        current_keywords=current,
        pinned=pinned,
        min_keywords=args.min_keywords,
        max_keywords=args.max_keywords,
        min_runs_before_swap=args.min_runs,
        ingest_run_count=len(runs),
    )


async def async_main(args: argparse.Namespace) -> int:
    plan = await plan_rotation(args)
    print(markdown_plan(plan))

    if args.apply and plan.changed:
        write_scheduled_keywords(args.config, args.narrative, plan.after)
        reset_rotation_state(args.rotation_state, plan.after)
        append_rotation_log(plan, args.log)
        print(f"Applied rotation → {args.config}")
    elif args.apply:
        print("No changes applied.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("-s", "--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--narrative", default="midterms_2026")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--post-limit", type=int, default=500)
    parser.add_argument("--min-keywords", type=int, default=MIN_KEYWORDS)
    parser.add_argument("--max-keywords", type=int, default=MAX_KEYWORDS)
    parser.add_argument("--min-runs", type=int, default=MIN_RUNS_BEFORE_SWAP)
    parser.add_argument(
        "--pin",
        nargs="*",
        help=f"Keywords never auto-removed (default: {', '.join(DEFAULT_PINNED)}).",
    )
    parser.add_argument("--rotation-state", type=Path, default=DEFAULT_ROTATION_STATE)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--apply", action="store_true", help="Write scheduled_ingest.json")
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
