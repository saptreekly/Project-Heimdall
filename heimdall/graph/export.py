from dataclasses import dataclass, field

from sqlalchemy import String, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.datasets.astroturf import lookup_labels
from heimdall.db.models import InteractionEdge, Narrative, OutrageScore, Platform, Post
from heimdall.graph.networkx_analysis import NarrativeGraphAnalyzer


def _normalize_platform(raw: str) -> str:
    key = (raw or "").strip().lower()
    try:
        return Platform(key).value
    except ValueError:
        return key or "unknown"


@dataclass
class GraphExportPayload:
    narrative_id: int
    narrative_name: str
    keywords: str
    authors: list[dict] = field(default_factory=list)
    posts: list[dict] = field(default_factory=list)
    amplifications: list[dict] = field(default_factory=list)
    cib: dict | None = None


async def build_graph_export(
    session: AsyncSession,
    narrative_id: int,
    *,
    include_cib: bool = True,
) -> GraphExportPayload:
    narrative = await session.get(Narrative, narrative_id)
    if not narrative:
        raise ValueError(f"Narrative {narrative_id} not found")

    # Cast platform to string so legacy rows (e.g. MOCK) do not break Enum coercion.
    posts_result = await session.execute(
        select(
            Post.id,
            Post.external_id,
            cast(Post.platform, String),
            Post.author_id,
            Post.author_handle,
            Post.text,
            Post.posted_at,
            OutrageScore.outrage_index,
            OutrageScore.sentiment_label,
        )
        .outerjoin(OutrageScore, OutrageScore.post_id == Post.id)
        .where(Post.narrative_id == narrative_id)
    )
    rows = posts_result.all()

    x_author_ids = list(
        {
            author_id
            for _pid, _eid, platform_raw, author_id, *_rest in rows
            if _normalize_platform(platform_raw) == Platform.X.value
        }
    )
    bot_labels = await lookup_labels(session, x_author_ids)

    author_map: dict[str, dict] = {}
    post_rows: list[dict] = []
    for (
        post_id,
        external_id,
        platform_raw,
        author_id,
        author_handle,
        text,
        posted_at,
        outrage_index,
        sentiment_label,
    ) in rows:
        outrage = outrage_index if outrage_index is not None else 0.0
        platform = _normalize_platform(platform_raw)
        post_rows.append(
            {
                "post_id": post_id,
                "external_id": external_id,
                "platform": platform,
                "author_id": author_id,
                "handle": author_handle,
                "text": text[:500],
                "posted_at": posted_at.isoformat(),
                "outrage_index": outrage,
                "sentiment_label": sentiment_label,
            }
        )
        existing = author_map.get(author_id)
        bot_label = bot_labels.get(author_id)
        if not existing:
            author_map[author_id] = {
                "author_id": author_id,
                "handle": author_handle,
                "max_outrage": outrage,
                "post_count": 1,
                "known_bot": bot_label is not None,
                "bot_label": bot_label,
            }
        else:
            existing["post_count"] += 1
            existing["max_outrage"] = max(existing["max_outrage"], outrage)
            if author_handle:
                existing["handle"] = author_handle
            if bot_label:
                existing["known_bot"] = True
                existing["bot_label"] = bot_label

    edges_result = await session.execute(
        select(
            InteractionEdge.source_author_id,
            InteractionEdge.target_author_id,
            cast(InteractionEdge.interaction_type, String),
            InteractionEdge.source_post_id,
            InteractionEdge.target_post_id,
            InteractionEdge.occurred_at,
        ).where(InteractionEdge.narrative_id == narrative_id)
    )
    amplifications = [
        {
            "source": source,
            "target": target,
            "type": (itype or "").strip().lower(),
            "source_post_id": source_post_id,
            "target_post_id": target_post_id,
            "occurred_at": occurred_at.isoformat() if occurred_at else None,
        }
        for source, target, itype, source_post_id, target_post_id, occurred_at in edges_result.all()
    ]

    cib_data = None
    if include_cib:
        assessment = await NarrativeGraphAnalyzer().assess_narrative(session, narrative_id)
        m = assessment.metrics
        cib_data = {
            "suspicion_score": assessment.suspicion_score,
            "organic_score": m.organic_score,
            "signals": assessment.signals,
            "node_count": m.node_count,
            "edge_count": m.edge_count,
            "density": m.density,
        }

    return GraphExportPayload(
        narrative_id=narrative_id,
        narrative_name=narrative.name,
        keywords=narrative.keywords,
        authors=list(author_map.values()),
        posts=post_rows,
        amplifications=amplifications,
        cib=cib_data,
    )
