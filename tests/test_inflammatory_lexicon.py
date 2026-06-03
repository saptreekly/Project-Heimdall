from heimdall.nlp.lexicon import inflammatory_strength


def test_inflammatory_strength_counts_families() -> None:
    strength, hits = inflammatory_strength(
        "Deep state vermin — wake up and fight back before they censor this."
    )
    assert hits >= 3
    assert strength >= 0.5


def test_inflammatory_strength_zero_for_civil_text() -> None:
    strength, hits = inflammatory_strength(
        "I disagree with the policy but respect opposing views."
    )
    assert hits == 0
    assert strength == 0.0
