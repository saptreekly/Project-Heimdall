"""Build CIB / coordination report with split graph vs text scores."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.analysis.coordination_scores import (
    collect_text_signals,
    compute_text_coordination_score,
    graph_coverage_pct,
    is_graph_sufficient,
    merge_coordination_scores,
)
from heimdall.analysis.cross_pollination import cross_pollination_cib_signals
from heimdall.analysis.duplicates import find_duplicate_clusters_from_rows
from heimdall.analysis.near_duplicates import find_cross_author_fuzzy_clusters
from heimdall.api.schemas import CIBResponse
from heimdall.datasets.astroturf import narrative_bot_overlap
from heimdall.export.cross_pollination_loader import per_narrative_hits
from heimdall.graph.networkx_analysis import NarrativeGraphAnalyzer
from heimdall.db.models import Post


async def build_cib_report(
    db: AsyncSession,
    narrative_id: int,
    *,
    cross_pollination_report: dict | None = None,
    graph_stats: dict | None = None,
) -> CIBResponse:
    analyzer = NarrativeGraphAnalyzer()
    assessment = await analyzer.assess_narrative(db, narrative_id)
    m = assessment.metrics

    dup_rows = await db.execute(
        select(Post.id, Post.author_id, Post.text, Post.posted_at).where(
            Post.narrative_id == narrative_id
        )
    )
    dup_list = list(dup_rows.all())
    duplicate_clusters = find_duplicate_clusters_from_rows(dup_list)
    near_rows = [
        (pid, author_id, text, posted_at.isoformat())
        for pid, author_id, text, posted_at in dup_list
    ]
    cross_fuzzy = find_cross_author_fuzzy_clusters(near_rows)

    pollination_hits = 0
    pollination_signals: list[str] = []
    if cross_pollination_report:
        pollination_signals = cross_pollination_cib_signals(
            cross_pollination_report, narrative_id
        )
        pollination_hits = per_narrative_hits(cross_pollination_report, narrative_id).get(
            "hit_count", 0
        )

    graph_score = assessment.suspicion_score
    graph_signals = list(assessment.signals)
    text_score = compute_text_coordination_score(
        duplicate_clusters,
        cross_fuzzy,
        pollination_hit_count=pollination_hits,
    )
    text_signals = collect_text_signals(duplicate_clusters, cross_fuzzy)
    combined, organic = merge_coordination_scores(graph_score, text_score)

    stats = graph_stats or {}
    connected = int(stats.get("connected_author_count", 0))
    author_count = int(stats.get("author_count", m.node_count))
    edge_count = int(stats.get("edge_count", m.edge_count))
    coverage = graph_coverage_pct(connected, author_count)
    graph_ok = is_graph_sufficient(edge_count, connected, author_count)

    bot_overlap = await narrative_bot_overlap(db, narrative_id)
    return CIBResponse(
        narrative_id=narrative_id,
        suspicion_score=combined,
        organic_score=organic,
        graph_suspicion_score=graph_score,
        text_coordination_score=text_score,
        graph_sufficient=graph_ok,
        graph_coverage_pct=coverage,
        signals=graph_signals + text_signals + pollination_signals,
        graph_signals=graph_signals,
        text_signals=text_signals,
        node_count=m.node_count,
        edge_count=m.edge_count,
        density=m.density,
        top_amplifiers=m.top_amplifiers,
        coordinated_clusters=m.coordinated_clusters,
        iu_astroturf=bot_overlap,
    )
