from heimdall.nlp.outrage import MODEL_VERSION, MODEL_VERSION_EMBED
from scripts.verify_snapshot import validate_sentiment_bundle


def test_validate_sentiment_bundle_strict_requires_new_fields():
    bundle = {
        "sentiment": {"buckets": [], "trend": "stable"},
        "posts": [{"outrage_index": 0.1}],
        "provenance": {"outrage_model_version": "heimdall-lexicon-v2.2"},
    }
    assert validate_sentiment_bundle(bundle, strict=False) == []
    errors = validate_sentiment_bundle(bundle, strict=True)
    assert any("divergence_days" in e for e in errors)
    assert any("polarity" in e for e in errors)
    assert any(MODEL_VERSION in e for e in errors)


def test_validate_sentiment_bundle_ok_when_complete():
    bundle = {
        "sentiment": {
            "buckets": [{"date": "2026-01-01", "mean_outrage": 0.1, "count": 1}],
            "trend": "stable",
            "divergence_days": [],
            "week_over_week": {"available": False},
        },
        "posts": [
            {
                "outrage_index": 0.1,
                "polarity": "neutral",
                "escalation_tier": "neutral",
                "negativity_score": 0.0,
            }
        ],
        "provenance": {"outrage_model_version": MODEL_VERSION_EMBED},
    }
    assert validate_sentiment_bundle(bundle, strict=True) == []
