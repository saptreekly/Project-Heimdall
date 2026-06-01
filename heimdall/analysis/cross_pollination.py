"""Cross-narrative author overlap — threat actors spanning multiple keyword silos."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NarrativePresence:
    narrative_id: int
    narrative_name: str
    post_count: int
    max_outrage: float | None
    first_seen: str | None
    last_seen: str | None


@dataclass(frozen=True)
class CrossPollinationActor:
    """Author account active in multiple narratives (organized proxy indicator)."""

    actor_key: str
    platform: str
    author_id: str
    author_handle: str | None
    narrative_count: int
    total_posts: int
    pollination_score: float
    narratives: list[NarrativePresence]
    span_days: float


@dataclass(frozen=True)
class NarrativePairOverlap:
    narrative_a_id: int
    narrative_a_name: str
    narrative_b_id: int
    narrative_b_name: str
    shared_actor_count: int


def _actor_key(platform: str, author_id: str) -> str:
    return f"{(platform or 'unknown').lower()}:{author_id}"


def _parse_iso(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _span_days(timestamps: list[datetime | None]) -> float:
    valid = [t for t in timestamps if t is not None]
    if len(valid) < 2:
        return 0.0
    return round((max(valid) - min(valid)).total_seconds() / 86400, 2)


def pollination_score(narrative_count: int, total_posts: int, span_days: float) -> float:
    """
    Higher when an actor spans more narratives with sustained volume.

    Roughly: narratives * log2(posts+1) * mild span bonus (capped).
    """
    if narrative_count < 2:
        return 0.0
    base = narrative_count * math.log2(total_posts + 1)
    span_bonus = min(1.5, 1.0 + span_days / 30.0) if span_days > 0 else 1.0
    return round(base * span_bonus, 4)


def build_cross_pollination_report(
    rows: list[tuple],
    *,
    min_narratives: int = 2,
    min_posts_total: int = 2,
    max_actors: int = 50,
    max_pairs: int = 30,
) -> dict:
    """
    Build cross-pollination report from aggregated DB rows.

    Each row:
      (narrative_id, narrative_name, platform, author_id, author_handle,
       post_count, max_outrage, first_seen, last_seen)
    """
    by_actor: dict[str, dict] = {}

    for row in rows:
        (
            narrative_id,
            narrative_name,
            platform,
            author_id,
            author_handle,
            post_count,
            max_outrage,
            first_seen,
            last_seen,
        ) = row
        if not author_id:
            continue
        key = _actor_key(str(platform), str(author_id))
        bucket = by_actor.setdefault(
            key,
            {
                "platform": str(platform),
                "author_id": str(author_id),
                "author_handle": None,
                "narratives": [],
                "timestamps": [],
            },
        )
        if author_handle and not bucket["author_handle"]:
            bucket["author_handle"] = str(author_handle)
        bucket["narratives"].append(
            NarrativePresence(
                narrative_id=int(narrative_id),
                narrative_name=str(narrative_name),
                post_count=int(post_count),
                max_outrage=float(max_outrage) if max_outrage is not None else None,
                first_seen=str(first_seen) if first_seen else None,
                last_seen=str(last_seen) if last_seen else None,
            )
        )
        for ts in (first_seen, last_seen):
            parsed = _parse_iso(ts)
            if parsed:
                bucket["timestamps"].append(parsed)

    actors: list[CrossPollinationActor] = []
    for key, bucket in by_actor.items():
        narratives = sorted(bucket["narratives"], key=lambda n: (-n.post_count, n.narrative_name))
        narrative_count = len(narratives)
        total_posts = sum(n.post_count for n in narratives)
        if narrative_count < min_narratives or total_posts < min_posts_total:
            continue
        span = _span_days(bucket["timestamps"])
        score = pollination_score(narrative_count, total_posts, span)
        actors.append(
            CrossPollinationActor(
                actor_key=key,
                platform=bucket["platform"],
                author_id=bucket["author_id"],
                author_handle=bucket["author_handle"],
                narrative_count=narrative_count,
                total_posts=total_posts,
                pollination_score=score,
                narratives=narratives,
                span_days=span,
            )
        )

    actors.sort(key=lambda a: (-a.pollination_score, -a.narrative_count, -a.total_posts))
    actors = actors[:max_actors]

    # Narrative pair overlap (shared actors)
    narrative_ids = sorted({n.narrative_id for a in actors for n in a.narratives})
    id_to_name = {n.narrative_id: n.narrative_name for a in actors for n in a.narratives}
    pair_counts: dict[tuple[int, int], int] = {}

    for actor in actors:
        nids = sorted({n.narrative_id for n in actor.narratives})
        for i in range(len(nids)):
            for j in range(i + 1, len(nids)):
                pair = (nids[i], nids[j])
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

    pairs: list[NarrativePairOverlap] = []
    for (a_id, b_id), count in sorted(pair_counts.items(), key=lambda x: -x[1]):
        pairs.append(
            NarrativePairOverlap(
                narrative_a_id=a_id,
                narrative_a_name=id_to_name.get(a_id, str(a_id)),
                narrative_b_id=b_id,
                narrative_b_name=id_to_name.get(b_id, str(b_id)),
                shared_actor_count=count,
            )
        )
    pairs = pairs[:max_pairs]

    return {
        "min_narratives": min_narratives,
        "actor_count": len(actors),
        "narrative_count": len(narrative_ids),
        "actors": [_actor_to_dict(a) for a in actors],
        "narrative_pairs": [_pair_to_dict(p) for p in pairs],
    }


def _actor_to_dict(actor: CrossPollinationActor) -> dict:
    return {
        "actor_key": actor.actor_key,
        "platform": actor.platform,
        "author_id": actor.author_id,
        "author_handle": actor.author_handle,
        "narrative_count": actor.narrative_count,
        "total_posts": actor.total_posts,
        "pollination_score": actor.pollination_score,
        "span_days": actor.span_days,
        "narratives": [
            {
                "narrative_id": n.narrative_id,
                "narrative_name": n.narrative_name,
                "post_count": n.post_count,
                "max_outrage": n.max_outrage,
                "first_seen": n.first_seen,
                "last_seen": n.last_seen,
            }
            for n in actor.narratives
        ],
    }


def _pair_to_dict(pair: NarrativePairOverlap) -> dict:
    return {
        "narrative_a_id": pair.narrative_a_id,
        "narrative_a_name": pair.narrative_a_name,
        "narrative_b_id": pair.narrative_b_id,
        "narrative_b_name": pair.narrative_b_name,
        "shared_actor_count": pair.shared_actor_count,
    }


def narrative_cross_pollination_hits(
    report: dict,
    narrative_id: int,
    *,
    max_hits: int = 25,
) -> dict:
    """Actors in this narrative who also appear in other narratives."""
    hits: list[dict] = []
    for actor in report.get("actors", []):
        narratives = actor.get("narratives", [])
        if not any(n.get("narrative_id") == narrative_id for n in narratives):
            continue
        other = [n for n in narratives if n.get("narrative_id") != narrative_id]
        if not other:
            continue
        hits.append(
            {
                **actor,
                "other_narratives": other,
                "other_narrative_count": len(other),
            }
        )
    hits.sort(key=lambda h: (-h.get("pollination_score", 0), -h.get("other_narrative_count", 0)))
    return {
        "narrative_id": narrative_id,
        "hit_count": len(hits),
        "actors": hits[:max_hits],
    }


def cross_pollination_cib_signals(report: dict, narrative_id: int) -> list[str]:
    """Signals when a narrative hosts multi-narrative actors."""
    hits = narrative_cross_pollination_hits(report, narrative_id)
    count = hits.get("hit_count", 0)
    if count == 0:
        return []
    top = hits.get("actors", [])[:3]
    signals = [f"cross_pollination_{count}_multi_narrative_actors"]
    for actor in top:
        names = ", ".join(
            n.get("narrative_name", "?") for n in actor.get("other_narratives", [])[:3]
        )
        handle = actor.get("author_handle") or actor.get("author_id", "")[:12]
        signals.append(f"cross_pollination_actor_{handle}_also_in_{names}")
    return signals
