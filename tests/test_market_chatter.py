from heimdall.nlp.market_chatter import (
    cluster_market_chatter_rate,
    is_market_chatter_cluster,
    is_market_chatter_post,
    market_chatter_score,
)

SAMPLE_MARKET = (
    "5/25-29 MKT/📈 BTC/GLD/SPX+1.4%/NDX+1.4% OpenHormuz\\10yR; "
    "Jensen GTC/COMPUTEX 2026 keynote /AI/Quantum SS GOP Midterms^GCC+EU+Asia"
)
SAMPLE_POLITICAL = (
    "Election fraud midterm vote accountability corrupt DOJ FBI stop gaslighting"
)


def test_market_chatter_score_high_for_fin_twit() -> None:
    score = market_chatter_score(SAMPLE_MARKET)
    assert score >= 0.42
    assert is_market_chatter_post(SAMPLE_MARKET)


def test_market_chatter_score_low_for_political_text() -> None:
    score = market_chatter_score(SAMPLE_POLITICAL)
    assert score < 0.42
    assert not is_market_chatter_post(SAMPLE_POLITICAL)


def test_cluster_market_detection() -> None:
    texts = [SAMPLE_MARKET, SAMPLE_MARKET.replace("BTC", "ETH")]
    assert cluster_market_chatter_rate(texts) >= 0.42
    assert is_market_chatter_cluster(texts, ["vix", "mkt", "btc", "ndx"])


def test_political_cluster_not_market() -> None:
    texts = [SAMPLE_POLITICAL, SAMPLE_POLITICAL.replace("FBI", "DOJ")]
    assert not is_market_chatter_cluster(texts, ["election", "fraud", "midterm"])
