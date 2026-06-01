"""Load cross-narrative author overlap from heimdall.db."""

from __future__ import annotations

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.analysis.cross_pollination import (
    build_cross_pollination_report,
    narrative_cross_pollination_hits,
)
from heimdall.db.models import Narrative, OutrageScore, Post


async def load_cross_pollination(db: AsyncSession) -> dict:
    """
    Scan all narratives in the database for authors active in multiple silos.
    """
    agg = await db.execute(
        select(
            Post.narrative_id,
            Narrative.name,
            cast(Post.platform, String),
            Post.author_id,
            func.max(Post.author_handle).label("author_handle"),
            func.count(Post.id).label("post_count"),
            func.max(OutrageScore.outrage_index).label("max_outrage"),
            func.min(Post.posted_at).label("first_seen"),
            func.max(Post.posted_at).label("last_seen"),
        )
        .join(Narrative, Narrative.id == Post.narrative_id)
        .outerjoin(OutrageScore, OutrageScore.post_id == Post.id)
        .group_by(
            Post.narrative_id,
            Narrative.name,
            cast(Post.platform, String),
            Post.author_id,
        )
    )
    rows = []
    for r in agg.all():
        rows.append(
            (
                r[0],
                r[1],
                r[2],
                r[3],
                r[4],
                r[5],
                r[6],
                r[7].isoformat() if r[7] else None,
                r[8].isoformat() if r[8] else None,
            )
        )

    report = build_cross_pollination_report(rows)
    report["available"] = len(rows) > 0
    return report


def per_narrative_hits(global_report: dict, narrative_id: int) -> dict:
    return narrative_cross_pollination_hits(global_report, narrative_id)
