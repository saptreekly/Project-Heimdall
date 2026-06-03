from heimdall.nlp.theme_phrases import (
    assign_distinct_phrase_labels,
    phrase_label_quality,
    rank_theme_labels,
    score_distinct_phrases,
)


def test_phrase_label_quality_rejects_fragments() -> None:
    assert phrase_label_quality("he's purposely") < 0.2
    assert phrase_label_quality("what's coming") < 0.2
    assert phrase_label_quality("hackers laying") < 0.25
    assert phrase_label_quality("feel sorry") < 0.2
    assert phrase_label_quality("executive order") >= 0.99
    assert phrase_label_quality("governor") >= 0.99


def test_rank_theme_labels_prefers_anchor_over_fragment() -> None:
    member = [
        "Governor race heating up — free and fair elections matter in every state.",
        "GOP could lose governor race if election fraud claims spread unchecked.",
        "Governor race turnout and election integrity on the ballot this fall.",
    ]
    contrast = [
        "He's purposely slow rolling Trump's agenda through executive orders.",
        "What's coming next from hackers laying groundwork to disrupt voting?",
        "Spread the word about house and senate races nationwide.",
    ]
    terms, phrases, distinctiveness = rank_theme_labels(member, contrast, top_n=6)
    assert terms, "expected theme terms"
    assert terms[0] in {"governor", "governor race", "election", "elections", "election integrity"}
    assert "he's purposely" not in terms
    assert "what's coming" not in terms
    assert distinctiveness > 0


def test_rank_theme_labels_keeps_known_phrases() -> None:
    member = [
        "Executive order on mail ballot rules ahead of midterm election.",
        "New executive order restricts mail ballot drop boxes statewide.",
        "Challenge to executive order over mail ballot access.",
    ]
    contrast = [
        "Random weather forecast and sports scores today.",
        "Cooking tips for summer grilling season.",
    ]
    terms, phrases, _ = rank_theme_labels(member, contrast, top_n=5)
    joined = " ".join(terms + phrases).lower()
    assert "executive order" in joined or "mail ballot" in joined


def test_score_distinct_skips_weak_bigram_lead() -> None:
    member = [
        "He's purposely slow rolling the agenda through every agency.",
        "Purposely slow rolling Trump's orders — wake up people.",
        "Slow rolling executive actions on purpose again.",
    ]
    contrast = [
        "Governor race and election fraud headlines dominate the news.",
        "Tina Peters convicted clerk election case update.",
    ]
    display, _fallback, _ = score_distinct_phrases(member, contrast, top_n=5)
    assert display
    assert display[0] not in {"he's purposely", "slow rolling", "what's coming"}


def test_assign_distinct_uses_theme_terms_and_phrases() -> None:
    cluster_texts = {
        0: [
            "Governor race free fair elections GOP lose swing state.",
            "Governor race election fraud claims in battleground.",
            "Free fair governor race turnout predictions.",
        ],
        1: [
            "He's purposely slow rolling Trump's agenda items.",
            "Slow rolling orders purposely delayed again.",
            "Purposely slow rolling every policy move.",
        ],
    }
    all_texts = [t for texts in cluster_texts.values() for t in texts]
    labels = assign_distinct_phrase_labels(cluster_texts, all_texts, top_n=5)
    gov_terms, gov_phrases, _ = labels[0]
    slow_terms, slow_phrases, _ = labels[1]
    assert gov_terms[0] in {"governor", "governor race", "election", "elections", "fair"}
    assert "he's purposely" not in slow_terms
    assert "slow rolling" not in slow_phrases or slow_terms[0] not in {"slow rolling", "he's purposely"}
