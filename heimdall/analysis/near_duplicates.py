"""Near-duplicate text: per-author spam loops and cross-author fuzzy amplification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from heimdall.analysis.duplicates import (
    SYNC_BURST_SUSPICION_FLOOR,
    SYNC_BURST_WINDOW_SECONDS,
    cluster_timing_metrics,
    normalize_text,
)

_WORD_RE = re.compile(r"[a-z0-9']+")

# Token Jaccard at or above this links posts in a fuzzy cluster (override via settings / env).
NEAR_DUPLICATE_JACCARD_THRESHOLD = 0.82
NEAR_DUPLICATE_JACCARD_MIN = 0.55
NEAR_DUPLICATE_JACCARD_MAX = 0.98
NEAR_DUPLICATE_JACCARD_STEP = 0.01
CROSS_AUTHOR_MIN_AUTHORS = 2
CROSS_AUTHOR_MIN_POSTS = 2


def jaccard_threshold_config(
    threshold: float = NEAR_DUPLICATE_JACCARD_THRESHOLD,
    *,
    threshold_min: float = NEAR_DUPLICATE_JACCARD_MIN,
    threshold_max: float = NEAR_DUPLICATE_JACCARD_MAX,
    threshold_step: float = NEAR_DUPLICATE_JACCARD_STEP,
) -> dict:
    """Metadata exported in snapshot for server default + client-side slider bounds."""
    return {
        "threshold": round(threshold, 4),
        "default_threshold": round(threshold, 4),
        "threshold_min": threshold_min,
        "threshold_max": threshold_max,
        "threshold_step": threshold_step,
        "threshold_live": True,
    }


def resolve_jaccard_threshold(
    override: float | None = None,
) -> tuple[float, float, float, float]:
    """Return (threshold, min, max, step) from settings when available."""
    if override is not None:
        return (
            override,
            NEAR_DUPLICATE_JACCARD_MIN,
            NEAR_DUPLICATE_JACCARD_MAX,
            NEAR_DUPLICATE_JACCARD_STEP,
        )
    try:
        from heimdall.config import get_settings

        s = get_settings()
        return (
            float(s.near_duplicate_jaccard_threshold),
            float(s.near_duplicate_jaccard_min),
            float(s.near_duplicate_jaccard_max),
            float(s.near_duplicate_jaccard_step),
        )
    except Exception:
        return (
            NEAR_DUPLICATE_JACCARD_THRESHOLD,
            NEAR_DUPLICATE_JACCARD_MIN,
            NEAR_DUPLICATE_JACCARD_MAX,
            NEAR_DUPLICATE_JACCARD_STEP,
        )


@dataclass(frozen=True)
class NearDuplicateGroup:
    """Same-author near-identical variants (local spam loop)."""

    group_id: int
    author_id: str
    post_ids: list[int]
    count: int
    sample_text: str
    max_similarity: float


@dataclass(frozen=True)
class CrossAuthorFuzzyCluster:
    """Fuzzy copypasta shared across multiple accounts (distributed astroturf)."""

    cluster_id: int
    post_ids: list[int]
    author_ids: list[str]
    author_count: int
    count: int
    sample_text: str
    max_similarity: float
    burst_synchronized: bool = False
    burst_author_count: int = 0
    cluster_span_seconds: float = 0.0
    min_inter_arrival_seconds: float | None = None


def token_set(text: str) -> set[str]:
    norm = normalize_text(text)
    return set(_WORD_RE.findall(norm))


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard(A, B) = |A ∩ B| / |A ∪ B| on word tokens."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union


def _union_find_clusters(
    n: int,
    pair_similarities: list[tuple[int, int, float]],
    *,
    min_size: int,
) -> list[tuple[list[int], float]]:
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    edge_max: dict[tuple[int, int], float] = {}
    for i, j, sim in pair_similarities:
        union(i, j)
        key = (min(i, j), max(i, j))
        edge_max[key] = max(edge_max.get(key, 0.0), sim)

    buckets: dict[int, list[int]] = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(i)

    out: list[tuple[list[int], float]] = []
    for indices in buckets.values():
        if len(indices) < min_size:
            continue
        sims = [
            edge_max[(min(a, b), max(a, b))]
            for a in indices
            for b in indices
            if a < b and (min(a, b), max(a, b)) in edge_max
        ]
        out.append((indices, max(sims) if sims else NEAR_DUPLICATE_JACCARD_THRESHOLD))
    return out


def _pairwise_similarities(
    items: list[tuple[int, str, set[str]]],
    *,
    threshold: float,
    require_distinct_authors: bool,
) -> list[tuple[int, int, float]]:
    pairs: list[tuple[int, int, float]] = []
    n = len(items)
    for i in range(n):
        _pid_i, author_i, tokens_i = items[i]
        for j in range(i + 1, n):
            _pid_j, author_j, tokens_j = items[j]
            if require_distinct_authors and author_i == author_j:
                continue
            sim = jaccard_similarity(tokens_i, tokens_j)
            if sim >= threshold:
                pairs.append((i, j, sim))
    return pairs


def find_near_duplicate_groups(
    rows: list[tuple[int, str, str, str]],
    *,
    threshold: float = NEAR_DUPLICATE_JACCARD_THRESHOLD,
    min_posts: int = 2,
) -> list[NearDuplicateGroup]:
    """
    Rows: (post_id, author_id, text, posted_at_iso).

    Intracluster: union-find within each author (local spam loops).
    """
    by_author: dict[str, list[tuple[int, str, set[str]]]] = {}
    for post_id, author_id, text, _posted_at in rows:
        tokens = token_set(text)
        if not tokens:
            continue
        by_author.setdefault(author_id, []).append((post_id, text, tokens))

    groups: list[NearDuplicateGroup] = []
    group_id = 0

    for author_id, items in by_author.items():
        if len(items) < min_posts:
            continue
        pairs = _pairwise_similarities(
            [(pid, author_id, tok) for pid, _text, tok in items],
            threshold=threshold,
            require_distinct_authors=False,
        )
        for indices, max_sim in _union_find_clusters(len(items), pairs, min_size=min_posts):
            post_ids = [items[i][0] for i in indices]
            sample = max((items[i][1] for i in indices), key=len)
            groups.append(
                NearDuplicateGroup(
                    group_id=group_id,
                    author_id=author_id,
                    post_ids=sorted(post_ids),
                    count=len(post_ids),
                    sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
                    max_similarity=round(max_sim, 4),
                )
            )
            group_id += 1

    groups.sort(key=lambda g: (-g.count, -g.max_similarity))
    return groups


def find_cross_author_fuzzy_clusters(
    rows: list[tuple[int, str, str, str]],
    *,
    threshold: float = NEAR_DUPLICATE_JACCARD_THRESHOLD,
    min_posts: int = CROSS_AUTHOR_MIN_POSTS,
    min_authors: int = CROSS_AUTHOR_MIN_AUTHORS,
) -> list[CrossAuthorFuzzyCluster]:
    """
    Cross-author fuzzy amplification: global union-find on token Jaccard.

    Only edges between distinct author_ids; components must include >= min_authors.
    Catches spinning copy (spacing/punctuation variants) across botnets.
    """
    items: list[tuple[int, str, str, set[str], str]] = []
    for post_id, author_id, text, posted_at in rows:
        tokens = token_set(text)
        if not tokens:
            continue
        items.append((post_id, author_id, text, tokens, posted_at))

    if len(items) < min_posts:
        return []

    indexed = [(pid, author, tok) for pid, author, _text, tok, _at in items]
    pairs = _pairwise_similarities(indexed, threshold=threshold, require_distinct_authors=True)

    clusters: list[CrossAuthorFuzzyCluster] = []
    cluster_id = 0

    for indices, max_sim in _union_find_clusters(len(items), pairs, min_size=min_posts):
        author_ids = sorted({items[i][1] for i in indices})
        if len(author_ids) < min_authors:
            continue

        post_ids = [items[i][0] for i in indices]
        sample = max((items[i][2] for i in indices), key=len)
        events = []
        for i in indices:
            posted_at = items[i][4]
            try:
                dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            events.append((dt, items[i][1]))
        timing = cluster_timing_metrics(events) if events else {}

        clusters.append(
            CrossAuthorFuzzyCluster(
                cluster_id=cluster_id,
                post_ids=sorted(post_ids),
                author_ids=author_ids,
                author_count=len(author_ids),
                count=len(post_ids),
                sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
                max_similarity=round(max_sim, 4),
                burst_synchronized=timing.get("burst_synchronized", False),
                burst_author_count=timing.get("burst_author_count", 0),
                cluster_span_seconds=timing.get("cluster_span_seconds", 0.0),
                min_inter_arrival_seconds=timing.get("min_inter_arrival_seconds"),
            )
        )
        cluster_id += 1

    clusters.sort(
        key=lambda c: (
            -int(c.burst_synchronized),
            -c.burst_author_count,
            -c.author_count,
            -c.count,
            -c.max_similarity,
        )
    )
    return clusters


def apply_cross_author_fuzzy_cib_boost(
    base_suspicion: float,
    base_signals: list[str],
    clusters: list[CrossAuthorFuzzyCluster],
) -> tuple[float, list[str]]:
    """Raise CIB suspicion when cross-author fuzzy clusters show coordinated timing."""
    signals = list(base_signals)
    suspicion = base_suspicion

    for cluster in clusters:
        if cluster.author_count < CROSS_AUTHOR_MIN_AUTHORS:
            continue
        signals.append(
            "cross_author_fuzzy_"
            f"{cluster.author_count}authors_{cluster.count}posts_j{cluster.max_similarity:.2f}"
        )
        if cluster.burst_synchronized:
            signals.append(
                "synchronized_fuzzy_burst_"
                f"{cluster.burst_author_count}_authors_in_{SYNC_BURST_WINDOW_SECONDS}s"
            )

    if any(c.burst_synchronized for c in clusters):
        suspicion = max(suspicion, SYNC_BURST_SUSPICION_FLOOR)
    elif any(c.author_count >= 3 for c in clusters):
        suspicion = max(suspicion, 0.55)

    return min(1.0, suspicion), signals


def post_id_to_near_group(groups: list[NearDuplicateGroup]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for group in groups:
        for pid in group.post_ids:
            mapping[pid] = group.group_id
    return mapping


def post_id_to_cross_author_cluster(clusters: list[CrossAuthorFuzzyCluster]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for cluster in clusters:
        for pid in cluster.post_ids:
            mapping[pid] = cluster.cluster_id
    return mapping


def _parse_posted_at(value: str | datetime) -> datetime | None:
    if isinstance(value, datetime):
        return value
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def author_spam_summaries(
    rows: list[tuple[int, str, str, str]],
    *,
    near_groups: list[NearDuplicateGroup],
    min_posts: int = 3,
) -> list[dict]:
    by_author: dict[str, list[tuple[int, str]]] = {}
    for post_id, author_id, _text, posted_at in rows:
        by_author.setdefault(author_id, []).append((post_id, posted_at))

    near_by_author = {g.author_id: g for g in near_groups if g.count >= min_posts}
    summaries: list[dict] = []

    for author_id, posts in by_author.items():
        if len(posts) < min_posts:
            continue
        dates = [_parse_posted_at(p[1]) for p in posts]
        valid = [d for d in dates if d is not None]
        span_hours = 0.0
        if len(valid) >= 2:
            span_hours = round((max(valid) - min(valid)).total_seconds() / 3600, 2)
        group = near_by_author.get(author_id)
        summaries.append(
            {
                "author_id": author_id,
                "post_count": len(posts),
                "post_ids": [p[0] for p in posts],
                "span_hours": span_hours,
                "near_duplicate_group_id": group.group_id if group else None,
                "near_duplicate_count": group.count if group else 0,
            }
        )

    summaries.sort(key=lambda s: (-s["post_count"], -s["near_duplicate_count"]))
    return summaries


def narrative_template_tokens(rows: list[tuple[int, str, str]]) -> set[str]:
    if not rows:
        return set()
    _pid, _author, longest = max(rows, key=lambda r: len(r[2]))
    return token_set(longest)


def copypasta_scores(
    rows: list[tuple[int, str, str]],
    *,
    template_tokens: set[str] | None = None,
) -> dict[int, float]:
    template = template_tokens if template_tokens is not None else narrative_template_tokens(rows)
    if not template:
        return {}
    out: dict[int, float] = {}
    for post_id, _author, text in rows:
        tokens = token_set(text)
        out[post_id] = round(jaccard_similarity(tokens, template), 4)
    return out
