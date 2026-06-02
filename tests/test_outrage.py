from heimdall.nlp.outrage import OutrageAnalyzer


def test_high_outrage_ragebait():
    analyzer = OutrageAnalyzer()
    result = analyzer.analyze(
        "They are destroying our country!!! WAKE UP - share before they delete this!!! "
        "The deep state vermin hate you."
    )
    assert result.outrage_index >= 0.33
    assert result.escalation_tier in ("escalating", "high_conflict")
    assert result.sentiment_label == result.escalation_tier
    assert result.polarity == "negative"
    assert result.dehumanization_score > 0
    assert result.anti_authority_score > 0
    assert result.ragebait_score > 0


def test_low_outrage_civil_discourse():
    analyzer = OutrageAnalyzer()
    result = analyzer.analyze(
        "I disagree with the policy on healthcare. We can debate the merits respectfully."
    )
    assert result.outrage_index < 0.4
    assert result.escalation_tier == "neutral"


def test_polarity_positive_for_affection():
    analyzer = OutrageAnalyzer()
    result = analyzer.analyze("Thank you for spreading love and gratitude today.")
    assert result.polarity in ("positive", "neutral")
    assert result.outrage_index < 0.15


def test_conspiracy_and_threat_boost_outrage():
    analyzer = OutrageAnalyzer()
    result = analyzer.analyze(
        "This is a false flag bioweapon agenda 2030 — bring guns and shoot them."
    )
    assert result.outrage_index >= 0.25
    assert result.negativity_score >= 0
