"""Load narrative posts and cluster themes in embedding space."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.config import get_settings
from heimdall.db.models import Post
from heimdall.nlp.embeddings import DEFAULT_EMBEDDING_MODEL
from heimdall.nlp.theme_clusters import ThemeClusterReport, cluster_posts, report_to_dict


async def narrative_theme_clusters(
    session: AsyncSession,
    narrative_id: int,
) -> dict:
    result = await session.execute(
        select(Post.id, Post.text).where(Post.narrative_id == narrative_id).order_by(Post.posted_at)
    )
    rows = [(int(r[0]), str(r[1])) for r in result.all()]
    settings = get_settings()
    report = cluster_posts(
        rows,
        narrative_id=narrative_id,
        model_name=settings.embedding_model or DEFAULT_EMBEDDING_MODEL,
    )
    return report_to_dict(report)


async def narrative_theme_report(
    session: AsyncSession,
    narrative_id: int,
) -> ThemeClusterReport:
    result = await session.execute(
        select(Post.id, Post.text).where(Post.narrative_id == narrative_id).order_by(Post.posted_at)
    )
    rows = [(int(r[0]), str(r[1])) for r in result.all()]
    settings = get_settings()
    return cluster_posts(
        rows,
        narrative_id=narrative_id,
        model_name=settings.embedding_model or DEFAULT_EMBEDDING_MODEL,
    )
