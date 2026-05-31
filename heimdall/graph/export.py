from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from heimdall.datasets.astroturf import lookup_labels
from heimdall.db.models import InteractionEdge, Narrative, OutrageScore, Post
from heimdall.graph.networkx_analysis import NarrativeGraphAnalyzer


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

    posts_result = await session.execute(
        select(Post)
        .where(Post.narrative_id == narrative_id)
        .options(joinedload(Post.scores))
    )
    posts = posts_result.unique().scalars().all()

    from heimdall.db.models import Platform

    x_author_ids = list({post.author_id for post in posts if post.platform == Platform.X})
    bot_labels = await lookup_labels(session, x_author_ids)

    author_map: dict[str, dict] = {}
    post_rows: list[dict] = []
    for post in posts:
        score = post.scores[0] if post.scores else None
        post_rows.append(
            {
                "post_id": post.id,
                "external_id": post.external_id,
                "platform": post.platform.value,
                "author_id": post.author_id,
                "handle": post.author_handle,
                "text": post.text[:500],
                "posted_at": post.posted_at.isoformat(),
                "outrage_index": score.outrage_index if score else 0.0,
                "sentiment_label": score.sentiment_label if score else None,
            }
        )
        existing = author_map.get(post.author_id)
        outrage = score.outrage_index if score else 0.0
        bot_label = bot_labels.get(post.author_id)
        if not existing:
            author_map[post.author_id] = {
                "author_id": post.author_id,
                "handle": post.author_handle,
                "max_outrage": outrage,
                "post_count": 1,
                "known_bot": bot_label is not None,
                "bot_label": bot_label,
            }
        else:
            existing["post_count"] += 1
            existing["max_outrage"] = max(existing["max_outrage"], outrage)
            if post.author_handle:
                existing["handle"] = post.author_handle
            if bot_label:
                existing["known_bot"] = True
                existing["bot_label"] = bot_label

    edges_result = await session.execute(
        select(InteractionEdge).where(InteractionEdge.narrative_id == narrative_id)
    )
    amplifications = [
        {
            "source": edge.source_author_id,
            "target": edge.target_author_id,
            "type": edge.interaction_type.value,
            "source_post_id": edge.source_post_id,
            "target_post_id": edge.target_post_id,
        }
        for edge in edges_result.scalars().all()
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
