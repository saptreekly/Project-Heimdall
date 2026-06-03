"""Attach cross-layer coordination metadata to theme clusters for the dashboard."""

from __future__ import annotations


def _overlap_refs(
    theme_post_ids: set[int],
    clusters: list[dict],
    *,
    id_key: str = "post_ids",
    ref_prefix: str = "exact",
) -> list[dict]:
    refs: list[dict] = []
    for index, cluster in enumerate(clusters):
        cluster_posts = set(cluster.get(id_key, []))
        overlap = cluster_posts & theme_post_ids
        if not overlap:
            continue
        refs.append(
            {
                "ref_id": f"{ref_prefix}_{index}",
                "overlap_count": len(overlap),
                "cluster_count": cluster.get("count", len(cluster_posts)),
                "author_count": cluster.get("author_count", len(cluster.get("author_ids", []))),
                "burst_synchronized": bool(cluster.get("burst_synchronized")),
                "sample_text": (cluster.get("sample_text") or "")[:160],
                "post_ids": sorted(overlap),
            }
        )
    refs.sort(key=lambda item: (-item["overlap_count"], -item["author_count"]))
    return refs


def classify_coordination_tier(
    *,
    exact_refs: list[dict],
    fuzzy_refs: list[dict],
    unique_author_count: int,
    unique_post_count: int,
    emerging_theme: bool,
) -> tuple[str, str]:
    has_burst_exact = any(
        ref.get("burst_synchronized") and int(ref.get("author_count", 0)) >= 3 for ref in exact_refs
    )
    has_exact_multi = any(int(ref.get("author_count", 0)) >= 3 for ref in exact_refs)
    has_fuzzy_burst = any(ref.get("burst_synchronized") for ref in fuzzy_refs)
    has_fuzzy = len(fuzzy_refs) > 0

    if has_burst_exact:
        return "high", "Template amplification"
    if has_exact_multi:
        return "high", "Exact duplicate campaign"
    if has_fuzzy_burst:
        return "medium", "Near-copy burst"
    if has_fuzzy:
        return "medium", "Near-copy campaign"
    if unique_author_count >= 3 and emerging_theme:
        return "medium", "Shared frame (emerging)"
    if unique_author_count >= 2 and unique_post_count >= 3:
        return "medium", "Shared frame"
    if unique_post_count <= 2:
        return "context", "Context only"
    return "low", "Distributed narrative"


def attach_coordination_overlays(
    theme_clusters: list[dict],
    amp_clusters: list[dict],
    fuzzy_clusters: list[dict],
    same_author_groups: list[dict],
    posts: list[dict],
) -> None:
    post_author = {int(p["id"]): p.get("author_id") for p in posts if p.get("id") is not None}

    for theme in theme_clusters:
        post_ids = {int(pid) for pid in theme.get("post_ids", [])}
        authors = {post_author[pid] for pid in post_ids if pid in post_author and post_author[pid]}
        exact_refs = _overlap_refs(post_ids, amp_clusters, ref_prefix="exact")
        fuzzy_refs = _overlap_refs(post_ids, fuzzy_clusters, ref_prefix="fuzzy")
        same_author_refs = _overlap_refs(post_ids, same_author_groups, ref_prefix="same_author")
        tier, tier_label = classify_coordination_tier(
            exact_refs=exact_refs,
            fuzzy_refs=fuzzy_refs,
            unique_author_count=len(authors),
            unique_post_count=len(post_ids),
            emerging_theme=bool(theme.get("emerging_theme")),
        )
        theme["coordination"] = {
            "unique_author_count": len(authors),
            "unique_post_count": len(post_ids),
            "exact_duplicate_clusters": exact_refs,
            "fuzzy_clusters": fuzzy_refs,
            "same_author_groups": same_author_refs,
            "tier": tier,
            "tier_label": tier_label,
        }
