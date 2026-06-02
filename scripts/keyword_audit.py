#!/usr/bin/env python3
"""
Keyword rotation audit + gap discovery.

Answers: which configured keywords return posts, and what distinctive themes
are we missing from scheduled_ingest.json?
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data" / "scheduled_ingest.json"
DEFAULT_RUNS = ROOT / "data" / "dashboard" / "ingest_runs.jsonl"
DEFAULT_SNAPSHOT = ROOT / "web" / "public" / "data" / "snapshot.json"
DEFAULT_DB = ROOT / "data" / "dashboard" / "heimdall.db"

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


@dataclass
class KeywordStats:
    keyword: str
    runs: int = 0
    fetched: int = 0
    inserted: int = 0
    skipped_runs: int = 0

    @property
    def yield_rate(self) -> float:
        if self.runs <= 0:
            return 0.0
        return self.inserted / self.runs


@dataclass
class SuggestedKeyword:
    query: str
    source: str
    score: float
    rationale: str


@dataclass
class KeywordAuditReport:
    window_days: int
    configured_keywords: list[str] = field(default_factory=list)
    stats: list[KeywordStats] = field(default_factory=list)
    dead_keywords: list[str] = field(default_factory=list)
    suggestions: list[SuggestedKeyword] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def keyword_covers(keyword: str, term: str) -> bool:
    kw = keyword.lower().strip()
    term_l = term.lower().strip()
    if not kw or not term_l:
        return False
    if term_l in kw or kw in term_l:
        return True
    kw_tokens = set(kw.split())
    term_tokens = set(term_l.split())
    return bool(kw_tokens & term_tokens)


def keyword_covers_any(keywords: list[str], term: str) -> bool:
    return any(keyword_covers(kw, term) for kw in keywords)


def load_ingest_runs(path: Path, *, days: int) -> list[dict]:
    if not path.is_file():
        return []
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        at_raw = row.get("at")
        if not at_raw:
            continue
        try:
            at = datetime.fromisoformat(str(at_raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if at.astimezone(UTC) >= cutoff:
            rows.append(row)
    return rows


def aggregate_keyword_stats(runs: list[dict], configured: list[str]) -> list[KeywordStats]:
    by_kw: dict[str, KeywordStats] = {k: KeywordStats(keyword=k) for k in configured}
    for row in runs:
        if row.get("skipped"):
            for kw in row.get("keywords") or []:
                if kw in by_kw:
                    by_kw[kw].skipped_runs += 1
            continue
        keywords = row.get("keywords") or row.get("planned_keywords") or []
        fetched = int(row.get("fetched") or 0)
        inserted = int(row.get("inserted") or 0)
        if len(keywords) == 1:
            kw = keywords[0]
            if kw not in by_kw:
                by_kw[kw] = KeywordStats(keyword=kw)
            stat = by_kw[kw]
            stat.runs += 1
            stat.fetched += fetched
            stat.inserted += inserted
        else:
            share = max(len(keywords), 1)
            for kw in keywords:
                if kw not in by_kw:
                    by_kw[kw] = KeywordStats(keyword=kw)
                by_kw[kw].runs += 1
                by_kw[kw].fetched += fetched // share
                by_kw[kw].inserted += inserted // share
    return [by_kw[k] for k in configured if k in by_kw] + [
        s for k, s in by_kw.items() if k not in configured
    ]


def _distinct_terms(texts: list[str], *, top_n: int = 40) -> list[tuple[str, float]]:
    from heimdall.nlp.theme_clusters import _corpus_term_rates, _score_distinct_terms

    if not texts:
        return []
    scored: Counter[str] = Counter()
    for idx, text in enumerate(texts):
        contrast = [t for j, t in enumerate(texts) if j != idx]
        for term, weight in _score_distinct_terms([text], _corpus_term_rates(contrast)):
            scored[term] += weight
    return scored.most_common(top_n)


def _theme_gap_terms(snapshot: dict, narrative_name: str) -> list[tuple[str, float, str]]:
    out: list[tuple[str, float, str]] = []
    for summary in snapshot.get("narratives") or []:
        if summary.get("name") != narrative_name:
            continue
        nid = str(summary["id"])
        themes = (snapshot.get("by_narrative_id") or {}).get(nid, {}).get("themes") or {}
        for cluster in themes.get("clusters") or []:
            distinct = float(cluster.get("label_distinctiveness") or 0)
            if distinct < 0.12:
                continue
            label = " · ".join((cluster.get("label_terms") or [])[:4])
            size = int(cluster.get("size") or 0)
            for term in cluster.get("label_terms") or []:
                out.append((term, distinct * size, f"theme cluster ({label}, {size} posts)"))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


async def _recent_post_texts(narrative_name: str, *, limit: int = 500) -> list[str]:
    from sqlalchemy import select

    from heimdall.db.models import Narrative, Post
    from heimdall.db.session import get_session_factory, init_db

    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        nid = await db.scalar(select(Narrative.id).where(Narrative.name == narrative_name))
        if nid is None:
            return []
        rows = (
            await db.execute(
                select(Post.text)
                .where(Post.narrative_id == nid)
                .order_by(Post.posted_at.desc())
                .limit(limit)
            )
        ).all()
        return [str(r[0]) for r in rows if r[0]]


def discover_gaps(
    configured: list[str],
    *,
    post_texts: list[str],
    theme_terms: list[tuple[str, float, str]],
    max_suggestions: int = 8,
) -> list[SuggestedKeyword]:
    suggestions: list[SuggestedKeyword] = []
    seen_queries: set[str] = set()
    midterms_context = "midterm" in " ".join(configured).lower()

    for term, score, source in theme_terms:
        if keyword_covers_any(configured, term):
            continue
        query = f"2026 {term}" if midterms_context else term
        if query in seen_queries:
            continue
        seen_queries.add(query)
        suggestions.append(
            SuggestedKeyword(
                query=query,
                source=source,
                score=round(score, 3),
                rationale="Distinctive theme term not matched by current keywords.",
            )
        )

    for term, weight in _distinct_terms(post_texts):
        if keyword_covers_any(configured, term):
            continue
        query = f"2026 {term} midterms" if midterms_context else term
        if query in seen_queries:
            continue
        seen_queries.add(query)
        suggestions.append(
            SuggestedKeyword(
                query=query,
                source="corpus c-TF-IDF",
                score=round(weight, 3),
                rationale="High-lift term in recent posts, uncovered by keyword list.",
            )
        )
        if len(suggestions) >= max_suggestions:
            break

    suggestions.sort(key=lambda s: s.score, reverse=True)
    return suggestions[:max_suggestions]


def build_report(
    *,
    config_path: Path,
    runs_path: Path,
    snapshot_path: Path,
    narrative_name: str,
    window_days: int,
    post_texts: list[str],
) -> KeywordAuditReport:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    configured: list[str] = []
    for job in config.get("jobs") or []:
        if job.get("narrative_name") == narrative_name:
            configured.extend(job.get("keywords") or [])

    runs = load_ingest_runs(runs_path, days=window_days)
    stats = aggregate_keyword_stats(runs, configured)
    dead = [s.keyword for s in stats if s.runs >= 2 and s.inserted == 0 and s.fetched == 0]

    snapshot = {}
    if snapshot_path.is_file():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    theme_terms = _theme_gap_terms(snapshot, narrative_name)
    suggestions = discover_gaps(configured, post_texts=post_texts, theme_terms=theme_terms)

    report = KeywordAuditReport(
        window_days=window_days,
        configured_keywords=configured,
        stats=sorted(stats, key=lambda s: (s.yield_rate, s.inserted)),
        dead_keywords=dead,
        suggestions=suggestions,
    )
    if not runs:
        report.notes.append(
            "No ingest_runs.jsonl entries in window — stats populate after scheduled ingest logging."
        )
    return report


def markdown_report(report: KeywordAuditReport) -> str:
    lines = [
        f"# Keyword audit — last {report.window_days} days",
        "",
        "## Configured keywords",
        "",
        "| Keyword | Runs | Fetched | Inserted | Yield (ins/run) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for stat in report.stats:
        lines.append(
            f"| {stat.keyword} | {stat.runs} | {stat.fetched} | {stat.inserted} | {stat.yield_rate:.2f} |"
        )
    lines.extend(["", "## Underperforming (0 inserts, 2+ runs)", ""])
    if report.dead_keywords:
        lines.extend(f"- `{kw}`" for kw in report.dead_keywords)
    else:
        lines.append("_None in window._")
    lines.extend(["", "## What are we missing?", ""])
    lines.append(
        "Suggested queries from theme clusters and corpus c-TF-IDF not covered by the keyword list."
    )
    lines.extend(["", "| Suggested query | Source | Score | Rationale |", "| --- | --- | ---: | --- |"])
    if report.suggestions:
        for sug in report.suggestions:
            lines.append(f"| `{sug.query}` | {sug.source} | {sug.score} | {sug.rationale} |")
    else:
        lines.append("| _none_ | — | — | All distinctive terms appear covered |")
    if report.notes:
        lines.extend(["", "## Notes", ""] + [f"- {n}" for n in report.notes])
    lines.append("")
    return "\n".join(lines)


def suggestions_json(report: KeywordAuditReport) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_days": report.window_days,
        "dead_keywords": report.dead_keywords,
        "suggestions": [
            {
                "query": s.query,
                "source": s.source,
                "score": s.score,
                "rationale": s.rationale,
            }
            for s in report.suggestions
        ],
    }


async def async_main(args: argparse.Namespace) -> int:
    import os

    if args.db.is_file():
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{args.db.resolve()}"

    post_texts = await _recent_post_texts(args.narrative, limit=args.post_limit)
    report = build_report(
        config_path=args.config,
        runs_path=args.runs,
        snapshot_path=args.snapshot,
        narrative_name=args.narrative,
        window_days=args.days,
        post_texts=post_texts,
    )

    md = markdown_report(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
    else:
        print(md)

    if args.suggestions_out:
        args.suggestions_out.parent.mkdir(parents=True, exist_ok=True)
        args.suggestions_out.write_text(
            json.dumps(suggestions_json(report), indent=2) + "\n",
            encoding="utf-8",
        )
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
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument(
        "--suggestions-out",
        type=Path,
        default=ROOT / "data" / "dashboard" / "keyword_suggestions.json",
    )
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
