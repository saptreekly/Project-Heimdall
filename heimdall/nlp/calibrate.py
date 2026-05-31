"""Compare lexicon outrage scores to TweetEval benchmark labels."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.datasets.tweet_eval import parse_tweet_eval_meta
from heimdall.db.models import OutrageScore, Platform, Post


async def tweet_eval_calibration(session: AsyncSession, narrative_id: int) -> dict:
    result = await session.execute(
        select(Post.text, Post.raw_json, OutrageScore.outrage_index)
        .join(OutrageScore, OutrageScore.post_id == Post.id)
        .where(
            Post.narrative_id == narrative_id,
            Post.platform == Platform.TWEET_EVAL,
        )
    )
    rows = result.all()
    if not rows:
        return {
            "narrative_id": narrative_id,
            "posts_scored": 0,
            "message": "No tweet_eval posts with outrage scores in this narrative.",
        }

    by_subset: dict[str, dict[str, list[float]]] = {}
    for _text, raw_json, outrage in rows:
        meta = parse_tweet_eval_meta(raw_json)
        if not meta:
            continue
        subset = meta["subset"]
        label_name = meta.get("label_name", str(meta.get("label")))
        by_subset.setdefault(subset, {}).setdefault(label_name, []).append(outrage)

    summaries = []
    for subset, labels in sorted(by_subset.items()):
        label_stats = []
        for label_name, scores in sorted(labels.items()):
            label_stats.append(
                {
                    "label": label_name,
                    "count": len(scores),
                    "mean_outrage": round(sum(scores) / len(scores), 4),
                }
            )
        label_stats.sort(key=lambda x: x["mean_outrage"], reverse=True)
        summaries.append({"subset": subset, "labels": label_stats})

    return {
        "narrative_id": narrative_id,
        "posts_scored": len(rows),
        "subsets": summaries,
        "hint": (
            "hate/offensive: positive class should have higher mean_outrage. "
            "stance_*: 'against' should exceed 'none'; scores are often lower than hate subset."
        ),
    }
