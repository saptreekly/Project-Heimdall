"""Near-duplicate text detection and temporal burst analysis for coordinated messaging."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

_WS_RE = re.compile(r"\s+")

# Coordinated drops: many distinct authors posting identical text in a tight window.
SYNC_BURST_WINDOW_SECONDS = 90
SYNC_BURST_MIN_AUTHORS = 5
SYNC_BURST_SUSPICION_FLOOR = 0.72


@dataclass(frozen=True)
class DuplicateCluster:
    normalized_text: str
    post_ids: list[int]
    author_ids: list[str]
    count: int
    sample_text: str
    burst_synchronized: bool = False
    burst_author_count: int = 0
    cluster_span_seconds: float = 0.0
    min_inter_arrival_seconds: float | None = None


def normalize_text(text: str, *, max_len: int = 280) -> str:
    lowered = (text or "").lower()
    lowered = _WS_RE.sub(" ", lowered).strip()
    return lowered[:max_len]


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def max_distinct_authors_in_window(
    events: list[tuple[datetime, str]],
    *,
    window_seconds: float = SYNC_BURST_WINDOW_SECONDS,
) -> int:
    """Sliding window: max distinct authors posting within window_seconds."""
    if not events:
        return 0
    ordered = sorted((_as_utc(t), author) for t, author in events)
    best = 0
    left = 0
    counts: dict[str, int] = {}
    distinct = 0

    for right in range(len(ordered)):
        t_right, author = ordered[right]
        if counts.get(author, 0) == 0:
            distinct += 1
        counts[author] = counts.get(author, 0) + 1

        while left <= right:
            t_left, _ = ordered[left]
            if (t_right - t_left).total_seconds() <= window_seconds:
                break
            a_left = ordered[left][1]
            counts[a_left] -= 1
            if counts[a_left] == 0:
                del counts[a_left]
                distinct -= 1
            left += 1

        best = max(best, distinct)

    return best


def cluster_timing_metrics(
    events: list[tuple[datetime, str]],
    *,
    window_seconds: float = SYNC_BURST_WINDOW_SECONDS,
    min_burst_authors: int = SYNC_BURST_MIN_AUTHORS,
) -> dict:
    """Inter-arrival and synchronized-burst metrics for one normalized-text cluster."""
    if not events:
        return {
            "burst_synchronized": False,
            "burst_author_count": 0,
            "cluster_span_seconds": 0.0,
            "min_inter_arrival_seconds": None,
        }

    times = sorted(_as_utc(t) for t, _ in events)
    span = (times[-1] - times[0]).total_seconds() if len(times) > 1 else 0.0
    deltas = [(t2 - t1).total_seconds() for t1, t2 in zip(times, times[1:], strict=False)]
    min_delta = min(deltas) if deltas else None

    burst_authors = max_distinct_authors_in_window(events, window_seconds=window_seconds)
    burst = burst_authors >= min_burst_authors

    return {
        "burst_synchronized": burst,
        "burst_author_count": burst_authors,
        "cluster_span_seconds": round(span, 2),
        "min_inter_arrival_seconds": round(min_delta, 2) if min_delta is not None else None,
    }


def apply_duplicate_temporal_cib_boost(
    base_suspicion: float,
    base_signals: list[str],
    clusters: list[DuplicateCluster],
) -> tuple[float, list[str]]:
    """Raise CIB suspicion when duplicate-text clusters show synchronized posting."""
    signals = list(base_signals)
    suspicion = base_suspicion

    for cluster in clusters:
        if not cluster.burst_synchronized:
            continue
        signals.append(
            "synchronized_duplicate_burst_"
            f"{cluster.burst_author_count}_authors_in_{SYNC_BURST_WINDOW_SECONDS}s"
        )

    if any(c.burst_synchronized for c in clusters):
        suspicion = max(suspicion, SYNC_BURST_SUSPICION_FLOOR)

    return min(1.0, suspicion), signals


def find_duplicate_clusters_from_rows(
    rows: list[tuple[int, str, str, datetime]],
    *,
    min_posts: int = 2,
) -> list[DuplicateCluster]:
    """Rows are (post_id, author_id, text, posted_at)."""
    buckets: dict[str, list[tuple[int, str, str, datetime]]] = {}
    for post_id, author_id, text, posted_at in rows:
        norm = normalize_text(text)
        if not norm:
            continue
        buckets.setdefault(norm, []).append((post_id, author_id, text, posted_at))

    clusters: list[DuplicateCluster] = []
    for norm, group in buckets.items():
        if len(group) < min_posts:
            continue
        sample = group[0][2]
        events = [(posted_at, author_id) for _, author_id, _, posted_at in group]
        timing = cluster_timing_metrics(events)

        clusters.append(
            DuplicateCluster(
                normalized_text=norm,
                post_ids=[p[0] for p in group],
                author_ids=sorted({p[1] for p in group}),
                count=len(group),
                sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
                burst_synchronized=timing["burst_synchronized"],
                burst_author_count=timing["burst_author_count"],
                cluster_span_seconds=timing["cluster_span_seconds"],
                min_inter_arrival_seconds=timing["min_inter_arrival_seconds"],
            )
        )
    clusters.sort(
        key=lambda c: (
            -int(c.burst_synchronized),
            -c.burst_author_count,
            -c.count,
            -len(c.author_ids),
        )
    )
    return clusters


def find_duplicate_text_clusters(
    posts: pd.DataFrame,
    *,
    min_posts: int = 2,
    text_col: str = "text",
    post_id_col: str = "post_id",
    author_col: str = "author_id",
    posted_at_col: str = "posted_at",
) -> list[DuplicateCluster]:
    if posts.empty or text_col not in posts.columns:
        return []

    cols = [post_id_col, author_col, text_col]
    if posted_at_col in posts.columns:
        cols.append(posted_at_col)
    working = posts[cols].copy()
    working["_norm"] = working[text_col].map(lambda t: normalize_text(str(t)))

    clusters: list[DuplicateCluster] = []
    for norm, group in working.groupby("_norm"):
        if not norm or len(group) < min_posts:
            continue
        if posted_at_col in group.columns:
            rows = [
                (
                    int(row[post_id_col]),
                    str(row[author_col]),
                    str(row[text_col]),
                    row[posted_at_col].to_pydatetime()
                    if hasattr(row[posted_at_col], "to_pydatetime")
                    else row[posted_at_col],
                )
                for _, row in group.iterrows()
            ]
            clusters.extend(find_duplicate_clusters_from_rows(rows, min_posts=min_posts))
            continue

        sample = str(group.iloc[0][text_col])
        clusters.append(
            DuplicateCluster(
                normalized_text=norm,
                post_ids=[int(x) for x in group[post_id_col].tolist()],
                author_ids=sorted({str(x) for x in group[author_col].tolist()}),
                count=len(group),
                sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
            )
        )

    clusters.sort(
        key=lambda c: (
            -int(c.burst_synchronized),
            -c.burst_author_count,
            -c.count,
            -len(c.author_ids),
        )
    )
    return clusters
