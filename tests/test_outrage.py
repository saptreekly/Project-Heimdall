from heimdall.nlp.outrage import OutrageAnalyzer


def test_high_outrage_ragebait():
    analyzer = OutrageAnalyzer()
    result = analyzer.analyze(
        "They are destroying our country!!! WAKE UP - share before they delete this!!! "
        "The deep state vermin hate you."
    )
    assert result.outrage_index >= 0.33
    assert result.sentiment_label in ("escalating", "high_conflict")
    assert result.dehumanization_score > 0
    assert result.anti_authority_score > 0


def test_low_outrage_civil_discourse():
    analyzer = OutrageAnalyzer()
    result = analyzer.analyze(
        "I disagree with the policy on healthcare. We can debate the merits respectfully."
    )
    assert result.outrage_index < 0.4
