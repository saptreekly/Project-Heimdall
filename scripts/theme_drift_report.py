#!/usr/bin/env python3
"""Compare theme clusters week-over-week — merges, splits, label drift."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "web" / "public" / "data" / "snapshot.json"
DEFAULT_BASELINE = ROOT / "data" / "dashboard" / "theme_baseline.json"
REPORTS_DIR = ROOT / "reports"


@dataclass
class ThemeDriftReport:
    narrative: str
    baseline_at: str | None
    current_at: str | None
    merged: list[str] = field(default_factory=list)
    split: list[str] = field(default_factory=list)
    vanished: list[str] = field(default_factory=list)
    emerged: list[str] = field(default_factory=list)
    label_drift: list[str] = field(default_factory=list)
    distinctiveness_drop: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _cluster_label(cluster: dict) -> str:
    terms = cluster.get("label_terms") or []
    if terms:
        return " · ".join(terms[:4])
    return f"cluster #{cluster.get('cluster_id', '?')}"


def _post_set(cluster: dict) -> set[int]:
    return {int(pid) for pid in (cluster.get("post_ids") or [])}


def _overlap(a: set[int], b: set[int]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _label_jaccard(a: dict, b: dict) -> float:
    ta = set(a.get("label_terms") or [])
    tb = set(b.get("label_terms") or [])
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def match_clusters(old: list[dict], new: list[dict], *, min_overlap: float = 0.35) -> list[tuple[dict | None, dict | None]]:
    used_new: set[int] = set()
    pairs: list[tuple[dict | None, dict | None]] = []

    for o in old:
        best_idx: int | None = None
        best_score = 0.0
        o_posts = _post_set(o)
        for idx, n in enumerate(new):
            if idx in used_new:
                continue
            score = _overlap(o_posts, _post_set(n))
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is not None and best_score >= min_overlap:
            used_new.add(best_idx)
            pairs.append((o, new[best_idx]))
        else:
            pairs.append((o, None))

    for idx, n in enumerate(new):
        if idx not in used_new:
            pairs.append((None, n))
    return pairs


def compare_themes(baseline: dict, current: dict, narrative_name: str) -> ThemeDriftReport:
    report = ThemeDriftReport(
        narrative=narrative_name,
        baseline_at=baseline.get("generated_at"),
        current_at=current.get("generated_at"),
    )
    old_clusters = baseline.get("clusters") or []
    new_clusters = current.get("clusters") or []

    if not old_clusters:
        report.notes.append("No baseline clusters — seeding baseline on this run.")
        for cluster in new_clusters:
            if float(cluster.get("label_distinctiveness") or 0) >= 0.12:
                report.emerged.append(_cluster_label(cluster))
        return report

    pairs = match_clusters(old_clusters, new_clusters)

    for o in old_clusters:
        matches = [n for op, n in pairs if op is o and n is not None]
        label = _cluster_label(o)
        if not matches:
            report.vanished.append(label)
        elif len(matches) > 1:
            report.split.append(f"{label} → {len(matches)} clusters")

    for n in new_clusters:
        matches = [op for op, np in pairs if np is n and op is not None]
        label = _cluster_label(n)
        if not matches:
            if float(n.get("label_distinctiveness") or 0) >= 0.12:
                report.emerged.append(label)
        elif len(matches) > 1:
            report.merged.append(f"{len(matches)} clusters → {label}")

    for o, n in pairs:
        if o is None or n is None:
            continue
        o_label = _cluster_label(o)
        n_label = _cluster_label(n)
        if _label_jaccard(o, n) < 0.35 and o_label != n_label:
            report.label_drift.append(f"{o_label} → {n_label}")
        old_d = float(o.get("label_distinctiveness") or 0)
        new_d = float(n.get("label_distinctiveness") or 0)
        if old_d - new_d >= 0.15:
            report.distinctiveness_drop.append(f"{n_label} ({old_d:.2f} → {new_d:.2f})")

    return report


def extract_theme_bundle(snapshot: dict, narrative_name: str | None = None) -> dict:
    for summary in snapshot.get("narratives") or []:
        name = summary.get("name")
        if narrative_name and name != narrative_name:
            continue
        nid = str(summary["id"])
        themes = (snapshot.get("by_narrative_id") or {}).get(nid, {}).get("themes") or {}
        return {
            "generated_at": snapshot.get("generated_at"),
            "narrative": name,
            "clusters": themes.get("clusters") or [],
        }
    return {"generated_at": snapshot.get("generated_at"), "narrative": narrative_name, "clusters": []}


def markdown_report(report: ThemeDriftReport) -> str:
    lines = [
        f"# Theme drift — {report.narrative}",
        "",
        f"_Baseline: {report.baseline_at or 'none'} · Current: {report.current_at or 'none'}_",
        "",
    ]
    sections = [
        ("Merged", report.merged),
        ("Split", report.split),
        ("Vanished", report.vanished),
        ("Emerged", report.emerged),
        ("Label drift", report.label_drift),
        ("Distinctiveness drop", report.distinctiveness_drop),
    ]
    for title, items in sections:
        lines.append(f"## {title}")
        lines.append("")
        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append("_None._")
        lines.append("")
    if report.notes:
        lines.append("## Notes")
        lines.extend(f"- {n}" for n in report.notes)
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-s", "--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--narrative", default="midterms_2026")
    parser.add_argument("-o", "--output", type=Path, help="Write markdown report here.")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    current = extract_theme_bundle(snapshot, args.narrative)

    baseline = {}
    if args.baseline.is_file():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        if baseline.get("narrative") != args.narrative:
            baseline = {}

    report = compare_themes(baseline, current, args.narrative)
    md = markdown_report(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
    else:
        print(md)

    if args.update_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
