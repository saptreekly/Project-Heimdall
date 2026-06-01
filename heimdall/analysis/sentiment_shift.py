"""Daily outrage buckets and regression-based sentiment trend classification."""

from __future__ import annotations

from datetime import datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.db.models import OutrageScore, Post

# Need enough days that one outlier day cannot dominate a two-point comparison.
MIN_BUCKETS_FOR_REGRESSION = 3
ROLLING_WINDOW = 3
# Minimum slope on smoothed daily means (outrage index is in [0, 1]).
MIN_SLOPE_PER_DAY = 0.008
# Require the linear fit to explain a meaningful share of variance (not a random walk).
MIN_R_SQUARED = 0.35


def build_daily_series(
    posted_at_outrage_pairs: list[tuple[datetime, float]],
) -> list[dict]:
    buckets: dict[str, list[float]] = {}
    for posted_at, outrage in posted_at_outrage_pairs:
        key = posted_at.strftime("%Y-%m-%d")
        buckets.setdefault(key, []).append(outrage)
    return [
        {"date": k, "mean_outrage": round(sum(v) / len(v), 4), "count": len(v)}
        for k, v in sorted(buckets.items())
    ]


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
    """Median pairwise slope; robust to a single outlier day."""
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
    """Drop the highest- and lowest-mean days before re-fitting."""
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
    """
    Classify daily mean-outrage trajectory using smoothed linear regression.

    Returns escalating, declining, stable, or insufficient_data.
    """
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


async def narrative_sentiment_shift(db: AsyncSession, narrative_id: int) -> dict:
    result = await db.execute(
        select(Post.posted_at, OutrageScore.outrage_index)
        .join(OutrageScore, OutrageScore.post_id == Post.id)
        .where(Post.narrative_id == narrative_id)
        .order_by(Post.posted_at)
    )
    rows = result.all()
    if not rows:
        return {"narrative_id": narrative_id, "buckets": [], "trend": "insufficient_data"}

    series = build_daily_series([(posted_at, outrage) for posted_at, outrage in rows])
    return {
        "narrative_id": narrative_id,
        "buckets": series,
        "trend": classify_trend(series),
    }
