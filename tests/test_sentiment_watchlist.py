from scripts.sentiment_watchlist import evaluate_alerts


def test_sentiment_wow_alert_fires_on_change():
    data = {
        "generated_at": "2026-06-01T00:00:00+00:00",
        "narratives": [{"id": 1, "name": "midterms_2026"}],
        "by_narrative_id": {
            "1": {
                "sentiment": {
                    "trend": "stable",
                    "week_over_week": {
                        "available": True,
                        "alert": "escalating_outrage",
                    },
                    "divergence_days": [],
                }
            }
        },
    }
    alerts, state = evaluate_alerts(data, {})
    assert len(alerts) == 1
    assert alerts[0].kind == "escalating_outrage"
    assert "midterms_2026" in state
