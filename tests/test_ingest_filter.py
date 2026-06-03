from heimdall.ingestion.ingest_filter import should_ingest_post


def test_market_post_filtered() -> None:
    text = "btc eth spy qqq vix mkt ndx spx call puts"
    result = should_ingest_post(text, narrative_keywords=["election"])
    assert not result.allow
    assert result.reason == "market_chatter"


def test_political_post_allowed() -> None:
    text = "election fraud midterm vote need accountability"
    result = should_ingest_post(text, narrative_keywords=["election", "fraud"])
    assert result.allow
