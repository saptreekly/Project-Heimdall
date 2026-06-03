from heimdall.nlp.theme_prefilter import (
    PrefilterReason,
    classify_post_for_clustering,
    is_promo_post,
    is_ultra_short_post,
)


def test_promo_detection() -> None:
    assert is_promo_post("Follow me for alpha https://x.com/a https://t.co/b")
    assert classify_post_for_clustering("Subscribe for daily calls") == PrefilterReason.PROMO


def test_ultra_short_filtered() -> None:
    assert is_ultra_short_post("ok")
    assert classify_post_for_clustering("too short") == PrefilterReason.SHORT


def test_political_text_stays_narrative() -> None:
    text = "election fraud midterm trump vote need accountability"
    assert classify_post_for_clustering(text, narrative_keywords=["election", "fraud"]) == PrefilterReason.NARRATIVE


def test_off_topic_when_keywords_miss() -> None:
    text = "random weather forecast sunny skies today"
    reason = classify_post_for_clustering(text, narrative_keywords=["election", "fraud"])
    assert reason == PrefilterReason.OFF_TOPIC
