"""Narrative briefing export — scales with corpus growth, embedded in snapshot + markdown artifacts."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_INGEST_LOG = Path("data/dashboard/ingest_runs.jsonl")


def _md_plain(text: str) -> str:
    return str(text or "").replace("\n", " ").replace("|", "\\|").strip()


def _truncate(text: str, limit: int = 200) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _safe_filename(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-").lower()
    return slug or "narrative"


def scaled_limit(total: int, *, floor: int = 3, ceiling: int = 12) -> int:
    if total <= floor:
        return total
    growth = floor + int(math.log2(max(total, 2)))
    return min(ceiling, max(floor, growth))


def load_ingest_yield(
    narrative_name: str,
    *,
    path: Path | None = None,
    days: int = 14,
) -> dict[str, Any]:
    log_path = path or Path(os.environ.get("INGEST_RUNS_PATH", DEFAULT_INGEST_LOG))
    if not log_path.is_file():
        return {"available": False, "runs": 0}

    cutoff = datetime.now(UTC) - timedelta(days=days)
    runs = 0
    net_new = 0
    duplicates = 0
    filtered = 0
    fetched = 0
    latest_at: str | None = None

    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("narrative_name") != narrative_name or row.get("skipped"):
            continue
        at_raw = row.get("at")
        if not at_raw:
            continue
        try:
            at = datetime.fromisoformat(str(at_raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        if at < cutoff:
            continue
        runs += 1
        net_new += int(row.get("net_new") or row.get("inserted") or 0)
        duplicates += int(row.get("duplicates") or 0)
        filtered += int(row.get("filtered") or 0)
        fetched += int(row.get("fetched") or 0)
        latest_at = str(at_raw)

    if runs == 0:
        return {"available": False, "runs": 0}

    processed = net_new + duplicates
    duplicate_rate = round(duplicates / max(processed, 1), 3) if processed else 0.0
    return {
        "available": True,
        "window_days": days,
        "runs": runs,
        "net_new": net_new,
        "duplicates": duplicates,
        "filtered": filtered,
        "fetched": fetched,
        "duplicate_rate": duplicate_rate,
        "latest_run_at": latest_at,
    }


def _label_terms(entry: dict) -> str:
    phrases = list(entry.get("label_phrases") or [])
    terms = list(entry.get("label_terms") or [])
    labels = phrases or terms
    if labels:
        return ", ".join(labels[:5])
    return f"cluster {entry.get('cluster_id', '?')}"


def _cluster_line(cluster: dict) -> str:
    return (
        f"- **{cluster.get('count', '?')} posts** · "
        f"{cluster.get('author_count', len(cluster.get('author_ids') or []))} author(s) — "
        f"{_md_plain(_truncate(cluster.get('sample_text') or '', 200))}"
    )


def _fuzzy_line(cluster: dict) -> str:
    pct = round(float(cluster.get("max_similarity") or 0) * 100)
    burst = " · **burst**" if cluster.get("burst_synchronized") else ""
    return (
        f"- **{cluster.get('count', '?')} posts** · "
        f"{cluster.get('author_count', '?')} authors · ~{pct}% Jaccard{burst} — "
        f"{_md_plain(_truncate(cluster.get('sample_text') or '', 200))}"
    )


def build_narrative_brief(
    *,
    narrative: dict,
    bundle: dict,
    cross_pollination: dict | None,
    generated_at: str,
) -> dict[str, Any]:
    """Build markdown + structured sections from a snapshot narrative bundle."""
    name = str(narrative.get("name") or narrative.get("id"))
    posts = bundle.get("posts") or []
    cib = bundle.get("cib") or {}
    amp = bundle.get("amplification") or {}
    near_dup = bundle.get("near_duplicates") or {}
    themes = bundle.get("themes") or {}
    sentiment = bundle.get("sentiment") or {}
    provenance = bundle.get("provenance") or {}
    pollination_hits = bundle.get("cross_pollination_hits") or {}
    sightings = themes.get("sightings") or {}

    posts_total_db = int(provenance.get("posts_total_db") or narrative.get("post_count") or len(posts))
    posts_in_snapshot = int(provenance.get("posts_in_snapshot") or len(posts))
    posts_truncated = bool(provenance.get("posts_truncated") or posts_total_db > posts_in_snapshot)

    amp_clusters = list(amp.get("clusters") or [])
    burst_all = [c for c in amp_clusters if c.get("burst_synchronized")]
    exact_all = [c for c in amp_clusters if not c.get("burst_synchronized")]
    fuzzy_all = list(near_dup.get("cross_author_fuzzy") or [])

    burst_limit = scaled_limit(len(burst_all), floor=2, ceiling=8)
    exact_limit = scaled_limit(len(exact_all), floor=3, ceiling=10)
    fuzzy_limit = scaled_limit(len(fuzzy_all), floor=3, ceiling=10)

    burst = burst_all[:burst_limit]
    exact = exact_all[:exact_limit]
    fuzzy = fuzzy_all[:fuzzy_limit]

    theme_source = themes.get("timeline") or themes.get("clusters") or []
    emerging_all = [t for t in theme_source if t.get("emerging_theme")]
    emerging_limit = scaled_limit(len(emerging_all), floor=3, ceiling=8)
    emerging = emerging_all[:emerging_limit]

    coordination_frames: list[dict] = []
    for cluster in themes.get("clusters") or []:
        coord = cluster.get("coordination") or {}
        tier = coord.get("tier")
        if tier in ("high", "medium"):
            coordination_frames.append(
                {
                    "cluster_id": cluster.get("cluster_id"),
                    "label": _label_terms(cluster),
                    "tier": tier,
                    "tier_label": coord.get("tier_label"),
                    "unique_post_count": coord.get("unique_post_count"),
                    "unique_author_count": coord.get("unique_author_count"),
                    "exact_subclusters": len(coord.get("exact_duplicate_clusters") or []),
                    "fuzzy_subclusters": len(coord.get("fuzzy_clusters") or []),
                }
            )
    coordination_frames.sort(
        key=lambda item: (
            0 if item.get("tier") == "high" else 1,
            -(item.get("unique_post_count") or 0),
        )
    )
    frame_limit = scaled_limit(len(coordination_frames) or len(theme_source), floor=3, ceiling=10)
    coordination_frames = coordination_frames[:frame_limit]

    ingest_yield = load_ingest_yield(name)
    global_actors = list((cross_pollination or {}).get("actors") or [])[:5]
    narrative_actors = list(pollination_hits.get("actors") or [])[:5]
    signals = list(cib.get("signals") or [])[: scaled_limit(len(cib.get("signals") or []), floor=6, ceiling=12)]

    wow = sentiment.get("week_over_week") or {}
    stamp = generated_at[:19].replace("T", " ") + " UTC"

    lines: list[str] = [
        f"# Heimdall briefing — {_md_plain(name)}",
        "",
        f"> Tactical snapshot · {stamp}",
        "",
        "## Corpus",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Posts in database | **{posts_total_db}** |",
        f"| Posts in snapshot cohort | {posts_in_snapshot} |",
        f"| Snapshot truncated | {'yes' if posts_truncated else 'no'} |",
        f"| CIB suspicion | **{float(cib.get('suspicion_score') or 0):.2f}** |",
        f"| Text coordination | {float(cib.get('text_coordination_score') or 0):.2f} |",
        f"| Graph suspicion | {float(cib.get('graph_suspicion_score') or 0):.2f} |",
        f"| Organic score | {float(cib.get('organic_score') or 0):.2f} |",
        f"| Graph nodes / edges | {cib.get('node_count', '?')} / {cib.get('edge_count', '?')} |",
        f"| Distinct themes | {themes.get('distinct_theme_count', '?')} |",
        f"| Duplicate clusters (full DB) | {provenance.get('duplicate_cluster_count', len(amp_clusters))} |",
        f"| Fuzzy clusters (snapshot cohort) | {provenance.get('fuzzy_cluster_count', len(fuzzy_all))} |",
    ]
    if cib.get("iu_astroturf"):
        iu = cib["iu_astroturf"]
        lines.append(
            f"| IU astroturf overlap | {iu.get('known_political_bots', '?')} bots / "
            f"{iu.get('authors_in_narrative', '?')} authors |"
        )
    lines.append("")

    if sightings.get("total_resightings"):
        lines.extend(
            [
                "## Ingest activity",
                "",
                f"- Re-sightings (duplicate encounters): **{sightings.get('total_resightings')}**",
                f"- Net-new posts logged: **{sightings.get('total_net_new', 0)}**",
                "",
            ]
        )

    if ingest_yield.get("available"):
        lines.extend(
            [
                f"## Ingest yield (last {ingest_yield.get('window_days')} days)",
                "",
                f"- Runs: **{ingest_yield.get('runs')}**",
                f"- Net new: **{ingest_yield.get('net_new')}** · re-seen: **{ingest_yield.get('duplicates')}**",
                f"- Duplicate rate: **{float(ingest_yield.get('duplicate_rate') or 0):.1%}**",
                "",
            ]
        )

    if sentiment.get("trend"):
        lines.extend(
            [
                "## Sentiment drift",
                "",
                f"- Trend: **{sentiment.get('trend')}**",
            ]
        )
        if wow.get("alert"):
            lines.append(f"- Week-over-week alert: **{wow.get('alert')}**")
        lines.append("")

    if coordination_frames:
        lines.extend(["## Layered coordination (frames)", ""])
        for frame in coordination_frames:
            lines.append(
                f"- **{frame.get('tier_label')}** · {_md_plain(frame.get('label') or '')} "
                f"({frame.get('unique_post_count')} posts · {frame.get('unique_author_count')} authors · "
                f"{frame.get('exact_subclusters')} exact · {frame.get('fuzzy_subclusters')} fuzzy subclusters)"
            )
        if len(coordination_frames) < len([c for c in themes.get('clusters') or [] if (c.get('coordination') or {}).get('tier') in ('high', 'medium')]):
            lines.append(f"- _…and more frames in dashboard._")
        lines.append("")

    lines.extend(["## CIB warning signals", ""])
    if signals:
        lines.extend(f"- {_md_plain(s)}" for s in signals)
    else:
        lines.append("_No elevated CIB signals in this snapshot._")
    lines.append("")

    lines.extend(["## Exact duplicate text (Layer 1 — copy coordination)", ""])
    if exact:
        lines.extend(_cluster_line(c) for c in exact)
        if len(exact_all) > len(exact):
            lines.append(f"- _…{len(exact_all) - len(exact)} more exact-duplicate cluster(s) in database._")
    else:
        lines.append("_None in full-database scan._")
    lines.append("")

    lines.extend(["## Synchronized bursts (exact text)", ""])
    if burst:
        lines.extend(_cluster_line(c) for c in burst)
        if len(burst_all) > len(burst):
            lines.append(f"- _…{len(burst_all) - len(burst)} more burst cluster(s)._")
    else:
        lines.append("_None (need ≥5 authors in 90s window)._")
    lines.append("")

    lines.extend(["## Cross-author fuzzy amplification (Layer 2 — frame coordination)", ""])
    if fuzzy:
        lines.extend(_fuzzy_line(c) for c in fuzzy)
        if len(fuzzy_all) > len(fuzzy):
            lines.append(f"- _…{len(fuzzy_all) - len(fuzzy)} more fuzzy cluster(s) in snapshot cohort._")
    else:
        lines.append("_None (Jaccard variants across ≥2 authors)._")
    lines.append("")

    lines.extend(["## Cross-narrative actors (this narrative)", ""])
    if narrative_actors:
        for actor in narrative_actors:
            handle = actor.get("author_handle") or actor.get("author_id")
            lines.append(
                f"- **{_md_plain(str(handle))}** · {actor.get('narrative_count', '?')} narratives · "
                f"score {float(actor.get('pollination_score') or 0):.2f}"
            )
    else:
        lines.append("_None flagged for this narrative._")
    lines.append("")

    lines.extend(["## Cross-narrative actors (global)", ""])
    if global_actors:
        for actor in global_actors:
            handle = actor.get("author_handle") or actor.get("author_id")
            silos = ", ".join(
                n.get("narrative_name", "?") for n in (actor.get("narratives") or [])[:4]
            )
            lines.append(
                f"- **{_md_plain(str(handle))}** · {actor.get('narrative_count', '?')} narratives "
                f"({ _md_plain(silos) }) · score {float(actor.get('pollination_score') or 0):.2f}"
            )
    else:
        lines.append("_None spanning multiple narratives._")
    lines.append("")

    lines.extend(["## Emerging themes", ""])
    if emerging:
        for theme in emerging:
            size = theme.get("size") or len(theme.get("post_ids") or [])
            lines.append(f"- {_md_plain(_label_terms(theme))} ({size} posts)")
        if len(emerging_all) > len(emerging):
            lines.append(f"- _…{len(emerging_all) - len(emerging)} more emerging theme(s)._")
    else:
        lines.append("_No emerging themes flagged._")
    lines.append("")

    if posts_truncated:
        lines.extend(
            [
                "## Scope note",
                "",
                f"Coordination dupes and CIB text signals scan **all {posts_total_db} database posts**. "
                f"Fuzzy clusters and sentiment charts use the **{posts_in_snapshot}-post snapshot cohort** "
                f"(limit {provenance.get('snapshot_post_limit', 250)}).",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "_Auto-generated at export · verify against live snapshot before operational use._",
        ]
    )

    markdown = "\n".join(lines)
    return {
        "version": 1,
        "generated_at": generated_at,
        "markdown": markdown,
        "meta": {
            "narrative_name": name,
            "posts_total_db": posts_total_db,
            "posts_in_snapshot": posts_in_snapshot,
            "posts_truncated": posts_truncated,
            "section_limits": {
                "exact": exact_limit,
                "burst": burst_limit,
                "fuzzy": fuzzy_limit,
                "emerging": emerging_limit,
                "frames": frame_limit,
                "signals": len(signals),
            },
            "totals": {
                "exact_duplicate_clusters": len(amp_clusters),
                "burst_clusters": len(burst_all),
                "fuzzy_clusters": len(fuzzy_all),
                "emerging_themes": len(emerging_all),
                "coordination_frames": len(coordination_frames),
            },
        },
        "sections": {
            "corpus": {
                "posts_total_db": posts_total_db,
                "posts_in_snapshot": posts_in_snapshot,
                "posts_truncated": posts_truncated,
                "cib_suspicion": cib.get("suspicion_score"),
                "text_coordination": cib.get("text_coordination_score"),
                "distinct_themes": themes.get("distinct_theme_count"),
            },
            "ingest_yield": ingest_yield,
            "sightings": sightings,
            "sentiment": {
                "trend": sentiment.get("trend"),
                "week_over_week_alert": wow.get("alert"),
            },
            "coordination_frames": coordination_frames,
            "signals": signals,
            "exact_duplicates": exact,
            "bursts": burst,
            "fuzzy": fuzzy,
            "emerging_themes": emerging,
            "cross_pollination_narrative": narrative_actors,
            "cross_pollination_global": global_actors,
        },
    }


def write_brief_artifacts(snapshot: dict, out_dir: Path) -> list[Path]:
    """Write per-narrative markdown briefs and an index file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = str(snapshot.get("generated_at") or datetime.now(UTC).isoformat())
    cross_pollination = snapshot.get("cross_pollination")
    by_id = snapshot.get("by_narrative_id") or {}
    written: list[Path] = []
    index_lines = [
        "# Heimdall narrative briefings",
        "",
        f"_Auto-generated · snapshot `{generated_at}`_",
        "",
        "| Narrative | DB posts | Brief |",
        "| --- | ---: | --- |",
    ]

    for summary in snapshot.get("narratives") or []:
        nid = str(summary["id"])
        bundle = by_id.get(nid, {})
        brief = bundle.get("brief")
        if not brief:
            brief = build_narrative_brief(
                narrative=summary,
                bundle=bundle,
                cross_pollination=cross_pollination,
                generated_at=generated_at,
            )
            bundle["brief"] = brief

        name = str(summary.get("name") or nid)
        slug = _safe_filename(name)
        path = out_dir / f"{slug}.md"
        path.write_text(str(brief.get("markdown") or ""), encoding="utf-8")
        written.append(path)

        posts_total = (brief.get("meta") or {}).get("posts_total_db") or summary.get("post_count") or "?"
        index_lines.append(f"| {name} | {posts_total} | [{slug}.md]({slug}.md) |")

    index_lines.append("")
    index_path = out_dir / "INDEX.md"
    index_path.write_text("\n".join(index_lines), encoding="utf-8")
    written.append(index_path)
    return written
