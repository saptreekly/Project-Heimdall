from heimdall.nlp.theme_phrases import cluster_lexical_relatedness


def test_generic_election_vocabulary_does_not_imply_relatedness() -> None:
    a = ["Trump election vote ballot senate house midterms."]
    b = ["Biden election vote ballot senate house midterms."]
    related, score = cluster_lexical_relatedness(a, b)
    assert not related
    assert score == 0.0


def test_same_known_phrase_still_related() -> None:
    a = ["Executive order on mail ballot rules nationwide."]
    b = ["Challenge to executive order over mail ballot access."]
    related, score = cluster_lexical_relatedness(a, b)
    assert related
    assert score == 1.0
