from heimdall.nlp.calibrate import _ranking_checks, _separation_score


def test_separation_score_orders_labels():
    stats = [
        {"label": "hate", "mean_outrage": 0.5},
        {"label": "non_hate", "mean_outrage": 0.2},
    ]
    assert _separation_score(stats) == 0.3


def test_ranking_checks_hate_subset():
    stats = [
        {"label": "hate", "mean_outrage": 0.4},
        {"label": "non_hate", "mean_outrage": 0.1},
    ]
    checks = _ranking_checks("hate", stats)
    assert "hate_beats_non_hate" in checks
