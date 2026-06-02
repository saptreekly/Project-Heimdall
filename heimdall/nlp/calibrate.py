"""Compare lexicon outrage scores to TweetEval benchmark labels."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.datasets.tweet_eval import LABEL_NAMES, parse_tweet_eval_meta
from heimdall.db.models import OutrageScore, Platform, Post
from heimdall.nlp.outrage import OutrageAnalyzer

BINARY_POSITIVE = {
    "hate": "hate",
    "offensive": "offensive",
    "irony": "irony",
}


def _ranking_checks(subset: str, label_stats: list[dict]) -> list[str]:
    by_label = {row["label"]: row["mean_outrage"] for row in label_stats}
    checks: list[str] = []

    if subset in BINARY_POSITIVE:
        pos = BINARY_POSITIVE[subset]
        neg = next((k for k in by_label if k != pos), None)
        if neg and by_label.get(pos, 0) > by_label.get(neg, 0):
            checks.append(f"{pos}_beats_{neg}")
        elif neg:
            checks.append(f"{pos}_below_{neg}")

    if subset == "sentiment":
        neg = by_label.get("negative", 0)
        neu = by_label.get("neutral", 0)
        pos = by_label.get("positive", 0)
        if neg > neu > pos or neg > pos:
            checks.append("negative_highest")
        else:
            checks.append("negative_not_highest")

    if subset.startswith("stance_"):
        against = by_label.get("against", 0)
        none = by_label.get("none", 0)
        if against > none:
            checks.append("against_beats_none")
        else:
            checks.append("against_below_none")

    return checks


def _separation_score(label_stats: list[dict]) -> float | None:
    if len(label_stats) < 2:
        return None
    highest = label_stats[0]["mean_outrage"]
    lowest = label_stats[-1]["mean_outrage"]
    return round(highest - lowest, 4)


async def tweet_eval_calibration(session: AsyncSession, narrative_id: int) -> dict:
    result = await session.execute(
        select(
            Post.text,
            Post.raw_json,
            OutrageScore.outrage_index,
            OutrageScore.polarity,
            OutrageScore.escalation_tier,
        )
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
    for _text, raw_json, outrage, _polarity, _tier in rows:
        meta = parse_tweet_eval_meta(raw_json)
        if not meta:
            continue
        subset = meta["subset"]
        label_name = meta.get("label_name", str(meta.get("label")))
        by_subset.setdefault(subset, {}).setdefault(label_name, []).append(outrage)

    summaries = []
    ranking_pass = 0
    ranking_total = 0
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
        checks = _ranking_checks(subset, label_stats)
        ranking_total += len(checks)
        ranking_pass += sum(1 for c in checks if not c.endswith("_below_") and "not_highest" not in c)
        summaries.append(
            {
                "subset": subset,
                "labels": label_stats,
                "separation": _separation_score(label_stats),
                "ranking_checks": checks,
            }
        )

    return {
        "narrative_id": narrative_id,
        "posts_scored": len(rows),
        "subsets": summaries,
        "ranking_pass_rate": round(ranking_pass / ranking_total, 3) if ranking_total else None,
        "hint": (
            "hate/offensive: positive class should have higher mean_outrage. "
            "sentiment: negative > neutral > positive. "
            "stance_*: 'against' should exceed 'none'."
        ),
    }


def benchmark_outrage_on_tweet_eval(
    subsets: list[str] | None = None,
    *,
    split: str = "test",
    limit_per_subset: int = 200,
    use_transformers: bool = False,
) -> dict:
    """
    Offline benchmark: score TweetEval rows in-process without DB persistence.
    """
    from heimdall.datasets.tweet_eval import _load_hf_dataset

    analyzer = OutrageAnalyzer(use_transformers=use_transformers)
    picked = subsets or ["hate", "offensive", "sentiment"]
    subset_reports: list[dict] = []

    for subset in picked:
        label_map = LABEL_NAMES.get(subset, {})
        dataset = _load_hf_dataset(subset, split)
        by_label: dict[str, list[float]] = {}
        for idx, row in enumerate(dataset):
            if idx >= limit_per_subset:
                break
            text = (row.get("text") or "").strip()
            if not text:
                continue
            label_name = label_map.get(int(row["label"]), str(row["label"]))
            score = analyzer.analyze(text).outrage_index
            by_label.setdefault(label_name, []).append(score)

        label_stats = [
            {
                "label": label,
                "count": len(scores),
                "mean_outrage": round(sum(scores) / len(scores), 4),
            }
            for label, scores in sorted(by_label.items())
        ]
        label_stats.sort(key=lambda x: x["mean_outrage"], reverse=True)
        subset_reports.append(
            {
                "subset": subset,
                "labels": label_stats,
                "separation": _separation_score(label_stats),
                "ranking_checks": _ranking_checks(subset, label_stats),
            }
        )

    return {
        "model_version": analyzer._model_version(),
        "split": split,
        "limit_per_subset": limit_per_subset,
        "transformer_sentiment": bool(analyzer._sentiment_pipe),
        "subsets": subset_reports,
    }
