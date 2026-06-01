from heimdall.analysis.near_duplicates import (
    NEAR_DUPLICATE_JACCARD_THRESHOLD,
    jaccard_threshold_config,
    resolve_jaccard_threshold,
)


def test_jaccard_threshold_config_shape() -> None:
    cfg = jaccard_threshold_config(0.75)
    assert cfg["threshold"] == 0.75
    assert cfg["default_threshold"] == 0.75
    assert cfg["threshold_live"] is True
    assert cfg["threshold_min"] < cfg["threshold_max"]


def test_resolve_jaccard_threshold_override() -> None:
    th, tmin, tmax, step = resolve_jaccard_threshold(0.7)
    assert th == 0.7
    assert tmin <= NEAR_DUPLICATE_JACCARD_THRESHOLD <= tmax
    assert step > 0
