"""Daily outrage buckets and regression-based sentiment trend classification."""

from __future__ import annotations

from datetime import datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.db.models import OutrageScore, Post

MIN_BUCKETS_FOR_REGRESSION = 3
ROLLING_WINDOW = 3
MIN_SLOPE_PER_DAY = 0.008
MIN_R_SQUARED = 0.35
DIVERGENCE_MEAN_OUTRAGE = 0.1
DIVERGENCE_VOLUME_MULTIPLIER = 1.5
DIVERGENCE_MIN_POSTS = 5
WOW_MIN_POSTS_PER_WEEK = 3
WOW_OUTRAGE_DELTA_ALERT = 0.06
WOW_VOLUME_SPIKE_PCT = 40.0

TIER_KEYS = ("neutral", "escalating", "high_conflict", "emerging_theme")
POLARITY_KEYS = ("negative", "neutral", "positive")


def build_daily_series(
    rows: list[tuple[datetime, float, str, str, float, float, float, float, float]],
) -> list[dict]:
    buckets: dict[str, dict] = {}
    for posted_at, outrage, escalation_tier, polarity, negativity, ragebait, stance, dehuman, anti_auth in rows:
        key = posted_at.strftime("%Y-%m-%d")
        bucket = buckets.setdefault(
            key,
            {
                "outrage": [],
                "negativity": [],
                "ragebait": [],
                "stance": [],
                "dehumanization": [],
                "anti_authority": [],
                "tier_counts": {k: 0 for k in TIER_KEYS},
                "polarity_counts": {k: 0 for k in POLARITY_KEYS},
            },
        )
        bucket["outrage"].append(outrage)
        bucket["negativity"].append(negativity)
        bucket["ragebait"].append(ragebait)
        bucket["stance"].append(stance)
        bucket["dehumanization"].append(dehuman)
        bucket["anti_authority"].append(anti_auth)
        tier = escalation_tier if escalation_tier in TIER_KEYS else "neutral"
        bucket["tier_counts"][tier] = bucket["tier_counts"].get(tier, 0) + 1
        pol = polarity if polarity in POLARITY_KEYS else "neutral"
        bucket["polarity_counts"][pol] = bucket["polarity_counts"].get(pol, 0) + 1

    series: list[dict] = []
    for key in sorted(buckets):
        b = buckets[key]
        count = len(b["outrage"])
        mean_outrage = round(sum(b["outrage"]) / count, 4)
        series.append(
            {
                "date": key,
                "mean_outrage": mean_outrage,
                "count": count,
                "mean_negativity": round(sum(b["negativity"]) / count, 4),
                "mean_ragebait": round(sum(b["ragebait"]) / count, 4),
                "mean_stance": round(sum(b["stance"]) / count, 4),
                "mean_dehumanization": round(sum(b["dehumanization"]) / count, 4),
                "mean_anti_authority": round(sum(b["anti_authority"]) / count, 4),
                "tier_counts": dict(b["tier_counts"]),
                "polarity_counts": dict(b["polarity_counts"]),
            }
        )
    return series


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    n = len(values)
    if n < window:
        return values
    w = min(window, n)
    kernel = np.ones(w, dtype=float) / w
    pad_left = w // 2
    pad_right = w - 1 - pad_left
    padded = np.pad(values, (pad_left, pad_right), mode="edge")
    smoothed = np.convolve(padded, kernel, mode="valid")
    if len(smoothed) != n:
        raise RuntimeError(f"rolling mean length mismatch: {len(smoothed)} != {n}")
    return smoothed


def _theil_sen_slope(x: np.ndarray, y: np.ndarray) -> float:
    slopes: list[float] = []
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            dx = float(x[j] - x[i])
            if abs(dx) < 1e-12:
                continue
            slopes.append((float(y[j]) - float(y[i])) / dx)
    if not slopes:
        return 0.0
    return float(np.median(slopes))


def _trim_outlier_day_indices(y: np.ndarray) -> np.ndarray:
    if len(y) < 4:
        return np.arange(len(y))
    i_max = int(np.argmax(y))
    i_min = int(np.argmin(y))
    exclude = {i_max} if i_max == i_min else {i_max, i_min}
    return np.array([i for i in range(len(y)) if i not in exclude], dtype=int)


def _r_squared(x: np.ndarray, y: np.ndarray, slope: float, intercept: float) -> float:
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    return 1.0 - (ss_res / ss_tot) if ss_tot > 1e-12 else 0.0


def classify_trend(series: list[dict]) -> str:
    n = len(series)
    if n < MIN_BUCKETS_FOR_REGRESSION:
        return "insufficient_data"

    y = np.array([float(b["mean_outrage"]) for b in series], dtype=float)
    y_smooth = _rolling_mean(y, ROLLING_WINDOW)
    x = np.arange(n, dtype=float)

    slope = _theil_sen_slope(x, y_smooth)
    intercept = float(np.median(y_smooth - slope * x))
    r_squared = _r_squared(x, y_smooth, slope, intercept)

    keep = _trim_outlier_day_indices(y_smooth)
    slope_trim = _theil_sen_slope(x[keep], y_smooth[keep]) if len(keep) >= 3 else 0.0

    def _significant(positive: bool) -> bool:
        if r_squared < MIN_R_SQUARED:
            return False
        if positive:
            return slope >= MIN_SLOPE_PER_DAY and slope_trim >= MIN_SLOPE_PER_DAY
        return slope <= -MIN_SLOPE_PER_DAY and slope_trim <= -MIN_SLOPE_PER_DAY

    if _significant(positive=True):
        return "escalating"
    if _significant(positive=False):
        return "declining"
    return "stable"


def detect_divergence_days(series: list[dict]) -> list[dict]:
    if not series:
        return []
    counts = [b["count"] for b in series]
    median_count = float(np.median(counts)) if counts else 0.0
    spike_threshold = max(DIVERGENCE_MIN_POSTS, median_count * DIVERGENCE_VOLUME_MULTIPLIER)
    divergent: list[dict] = []
    for bucket in series:
        if (
            bucket["count"] >= spike_threshold
            and bucket["mean_outrage"] < DIVERGENCE_MEAN_OUTRAGE
        ):
            divergent.append(
                {
                    "date": bucket["date"],
                    "count": bucket["count"],
                    "mean_outrage": bucket["mean_outrage"],
                }
            )
    return divergent


def week_over_week_shift(series: list[dict]) -> dict:
    if len(series) < 14:
        return {"available": False, "reason": "need_at_least_14_days"}

    recent = series[-7:]
    prior = series[-14:-7]
    recent_posts = sum(b["count"] for b in recent)
    prior_posts = sum(b["count"] for b in prior)
    if recent_posts < WOW_MIN_POSTS_PER_WEEK or prior_posts < WOW_MIN_POSTS_PER_WEEK:
        return {"available": False, "reason": "insufficient_posts_per_week"}

    def _weighted_mean(buckets: list[dict]) -> float:
        total = sum(b["count"] for b in buckets)
        if total == 0:
            return 0.0
        return sum(b["mean_outrage"] * b["count"] for b in buckets) / total

    recent_mean = _weighted_mean(recent)
    prior_mean = _weighted_mean(prior)
    mean_delta = round(recent_mean - prior_mean, 4)
    volume_delta_pct = round(
        ((recent_posts - prior_posts) / prior_posts) * 100.0 if prior_posts else 0.0,
        1,
    )

    alert: str | None = None
    if mean_delta >= WOW_OUTRAGE_DELTA_ALERT:
        alert = "escalating_outrage"
    elif volume_delta_pct >= WOW_VOLUME_SPIKE_PCT and recent_mean < DIVERGENCE_MEAN_OUTRAGE:
        alert = "volume_spike_low_outrage"

    return {
        "available": True,
        "recent_week_mean_outrage": round(recent_mean, 4),
        "prior_week_mean_outrage": round(prior_mean, 4),
        "mean_outrage_delta": mean_delta,
        "recent_week_posts": recent_posts,
        "prior_week_posts": prior_posts,
        "volume_delta_pct": volume_delta_pct,
        "alert": alert,
    }


async def narrative_sentiment_shift(
    db: AsyncSession,
    narrative_id: int,
    *,
    post_ids: list[int] | None = None,
) -> dict:
    q = (
        select(
            Post.posted_at,
            OutrageScore.outrage_index,
            OutrageScore.escalation_tier,
            OutrageScore.polarity,
            OutrageScore.negativity_score,
            OutrageScore.ragebait_score,
            OutrageScore.stance_score,
            OutrageScore.dehumanization_score,
            OutrageScore.anti_authority_score,
        )
        .join(OutrageScore, OutrageScore.post_id == Post.id)
        .where(Post.narrative_id == narrative_id)
        .order_by(Post.posted_at)
    )
    if post_ids is not None:
        if not post_ids:
            return _empty_response(narrative_id)
        q = q.where(Post.id.in_(post_ids))
    result = await db.execute(q)
    rows = result.all()
    if not rows:
        return _empty_response(narrative_id)

    series = build_daily_series(list(rows))
    divergence_days = detect_divergence_days(series)
    for bucket in series:
        bucket["volume_outrage_divergence"] = any(
            d["date"] == bucket["date"] for d in divergence_days
        )

    return {
        "narrative_id": narrative_id,
        "buckets": series,
        "trend": classify_trend(series),
        "divergence_days": divergence_days,
        "week_over_week": week_over_week_shift(series),
    }


def _empty_response(narrative_id: int) -> dict:
    return {
        "narrative_id": narrative_id,
        "buckets": [],
        "trend": "insufficient_data",
        "divergence_days": [],
        "week_over_week": {"available": False, "reason": "no_scored_posts"},
    }
