"""Same-author near-duplicate text and copypasta similarity (fuzzy, not exact-string match)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from heimdall.analysis.duplicates import normalize_text

_WORD_RE = re.compile(r"[a-z0-9']+")

# Same-author pairs at or above this Jaccard similarity are grouped.
NEAR_DUPLICATE_JACCARD_THRESHOLD = 0.82


@dataclass(frozen=True)
class NearDuplicateGroup:
    group_id: int
    author_id: str
    post_ids: list[int]
    count: int
    sample_text: str
    max_similarity: float


def token_set(text: str) -> set[str]:
    norm = normalize_text(text)
    return set(_WORD_RE.findall(norm))


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union


def find_near_duplicate_groups(
    rows: list[tuple[int, str, str, str]],
    *,
    threshold: float = NEAR_DUPLICATE_JACCARD_THRESHOLD,
    min_posts: int = 2,
) -> list[NearDuplicateGroup]:
    """
    Rows: (post_id, author_id, text, posted_at_iso).

    Groups posts by author, then union-finds pairs with Jaccard >= threshold.
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
        n = len(items)
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

        max_sim: dict[tuple[int, int], float] = {}
        for i in range(n):
            for j in range(i + 1, n):
                sim = jaccard_similarity(items[i][2], items[j][2])
                if sim >= threshold:
                    union(i, j)
                    max_sim[(i, j)] = sim

        buckets: dict[int, list[int]] = {}
        for i in range(n):
            buckets.setdefault(find(i), []).append(i)

        for indices in buckets.values():
            if len(indices) < min_posts:
                continue
            post_ids = [items[i][0] for i in indices]
            sample = max((items[i][1] for i in indices), key=len)
            pair_sims = [
                max_sim[(min(a, b), max(a, b))]
                for a in indices
                for b in indices
                if a < b and (min(a, b), max(a, b)) in max_sim
            ]
            groups.append(
                NearDuplicateGroup(
                    group_id=group_id,
                    author_id=author_id,
                    post_ids=sorted(post_ids),
                    count=len(post_ids),
                    sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
                    max_similarity=max(pair_sims) if pair_sims else threshold,
                )
            )
            group_id += 1

    groups.sort(key=lambda g: (-g.count, -g.max_similarity))
    return groups


def narrative_template_tokens(rows: list[tuple[int, str, str]]) -> set[str]:
    """Tokens from the longest post text (proxy for dominant copypasta template)."""
    if not rows:
        return set()
    _pid, _author, longest = max(rows, key=lambda r: len(r[2]))
    return token_set(longest)


def copypasta_scores(
    rows: list[tuple[int, str, str]],
    *,
    template_tokens: set[str] | None = None,
) -> dict[int, float]:
    """Per-post Jaccard similarity to the narrative template token set."""
    template = template_tokens if template_tokens is not None else narrative_template_tokens(rows)
    if not template:
        return {}
    out: dict[int, float] = {}
    for post_id, _author, text in rows:
        tokens = token_set(text)
        out[post_id] = round(jaccard_similarity(tokens, template), 4)
    return out


def post_id_to_near_group(groups: list[NearDuplicateGroup]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for group in groups:
        for pid in group.post_ids:
            mapping[pid] = group.group_id
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
    """Authors with many posts in the snapshot window."""
    by_author: dict[str, list[tuple[int, str]]] = {}
    for post_id, author_id, text, posted_at in rows:
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
