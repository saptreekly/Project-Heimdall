from heimdall.nlp.outrage import OutrageAnalyzer


def test_immigration_hate_scores_higher_than_affectionate_bitch():
    analyzer = OutrageAnalyzer()
    hate = analyzer.analyze(
        "Those People Invaded Us!!! They DO NOT BELONG HERE & HAVE NO RIGHTS! "
        "Its AmericaFIRST! NODACA!"
    )
    affection = analyzer.analyze("BITCH I LOVE YOU WITH MY WHOLE HEART UR MY FAVE ❤️")
    caps_fan = analyzer.analyze(
        "HE SPREADS LOVE AND I LEARNED TO APPRECIATE THE LGBTQ. I LOVE HIM."
    )
    assert hate.outrage_index > affection.outrage_index
    assert hate.outrage_index > caps_fan.outrage_index
    assert affection.outrage_index < 0.12
    assert caps_fan.outrage_index < 0.12


def test_offensive_profanity_without_affection():
    analyzer = OutrageAnalyzer()
    result = analyzer.analyze("BITCH DONT TEST ME")
    assert result.outrage_index >= 0.15
