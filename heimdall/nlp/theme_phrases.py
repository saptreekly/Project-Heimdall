"""Phrase extraction and filler filtering for theme cluster labels."""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9']{2,}")

# Social / platform noise
_PLATFORM_STOP = frozenset(
    {
        "amp",
        "com",
        "http",
        "https",
        "www",
        "rt",
        "via",
        "link",
        "nbsp",
        "twitter",
        "tweet",
        "retweet",
        "thread",
        "youtube",
        "tiktok",
    }
)

# High-frequency glue with little thematic signal in short posts
_FILLER_WORDS = frozenset(
    {
        "about",
        "after",
        "again",
        "all",
        "also",
        "any",
        "are",
        "back",
        "been",
        "being",
        "but",
        "can",
        "come",
        "could",
        "day",
        "did",
        "does",
        "doing",
        "don",
        "dont",
        "even",
        "every",
        "from",
        "get",
        "gets",
        "getting",
        "go",
        "going",
        "gone",
        "got",
        "had",
        "has",
        "have",
        "her",
        "here",
        "him",
        "his",
        "how",
        "into",
        "its",
        "just",
        "know",
        "let",
        "like",
        "look",
        "make",
        "many",
        "may",
        "more",
        "most",
        "much",
        "need",
        "new",
        "not",
        "now",
        "off",
        "one",
        "only",
        "our",
        "out",
        "over",
        "own",
        "people",
        "really",
        "said",
        "say",
        "says",
        "see",
        "she",
        "should",
        "some",
        "something",
        "still",
        "take",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "thing",
        "things",
        "think",
        "this",
        "those",
        "through",
        "time",
        "today",
        "too",
        "two",
        "use",
        "very",
        "want",
        "was",
        "way",
        "well",
        "were",
        "what",
        "when",
        "where",
        "who",
        "why",
        "will",
        "with",
        "would",
        "year",
        "you",
        "your",
    }
)

# Known multi-word frames — matched before token bigrams split them apart
KNOWN_PHRASES: tuple[str, ...] = (
    "red wave",
    "blue wave",
    "america first",
    "deep state",
    "stop the steal",
    "great replacement",
    "open border",
    "border crisis",
    "election fraud",
    "election integrity",
    "voter fraud",
    "mail ballot",
    "ballot harvesting",
    "executive order",
    "governor race",
    "midterm election",
    "fake news",
    "radical left",
    "radical right",
    "lock her up",
    "climate hoax",
    "mainstream media",
    "culture war",
    "law and order",
    "sanctuary city",
    "sanctuary cities",
    "welfare state",
    "second amendment",
    "gun control",
    "pro life",
    "pro choice",
)

KNOWN_PHRASES_SET = frozenset(KNOWN_PHRASES)

# Bigram/trigram fragments that PMI often over-ranks but aren't thematic anchors.
_FRAGMENT_PHRASES = frozenset(
    {
        "feel sorry",
        "he's purposely",
        "what's coming",
        "hackers laying",
        "slow rolling",
        "spread word",
        "word spread",
    }
)

_WEAK_START_TOKENS = frozenset(
    {
        "he",
        "she",
        "it",
        "we",
        "they",
        "what",
        "that",
        "this",
        "there",
        "here",
        "who",
        "how",
        "when",
        "where",
        "why",
        "he's",
        "she's",
        "it's",
        "we're",
        "they're",
        "what's",
        "that's",
        "who's",
        "here's",
        "there's",
        "feel",
        "felt",
    }
)

_WEAK_END_TOKENS = frozenset(
    {
        "laying",
        "coming",
        "going",
        "doing",
        "being",
        "getting",
        "making",
        "taking",
        "purposely",
        "slowly",
        "rolling",
        "spread",
        "sorry",
        "really",
        "just",
        "still",
        "again",
        "about",
        "around",
    }
)

_AUX_OR_GLUE = frozenset(
    {
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "purposely",
        "slowly",
    }
)

_THEME_STOPWORDS: frozenset[str] | None = None


def theme_stopwords() -> frozenset[str]:
    global _THEME_STOPWORDS
    if _THEME_STOPWORDS is None:
        try:
            from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

            base = set(ENGLISH_STOP_WORDS)
        except ImportError:
            base = set()
        base.update(_PLATFORM_STOP)
        base.update(_FILLER_WORDS)
        try:
            from heimdall.nlp.market_chatter import market_stopwords

            base.update(market_stopwords())
        except ImportError:
            pass
        _THEME_STOPWORDS = frozenset(base)
    return _THEME_STOPWORDS


def is_meaningful_token(word: str) -> bool:
    w = (word or "").lower().strip()
    if len(w) < 3 or w.isdigit():
        return False
    if w in theme_stopwords():
        return False
    # Drop lone sentiment adjectives that dominate but carry no frame
    if w in {"good", "bad", "best", "worst", "nice", "great", "big", "huge"}:
        return False
    return True


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if is_meaningful_token(t)]


def phrase_label_quality(phrase: str) -> float:
    """
    0–1 multiplier: penalize verb fragments and pronoun-led bigrams that PMI over-ranks.

    Unigrams pass through if the token itself is meaningful; known frames score highest.
    """
    normalized = (phrase or "").lower().strip()
    if not normalized:
        return 0.0
    if normalized in _FRAGMENT_PHRASES:
        return 0.05
    if normalized in KNOWN_PHRASES_SET:
        return 1.0

    parts = normalized.split()
    if len(parts) == 1:
        return 1.0 if is_meaningful_token(parts[0]) else 0.0

    if parts[0] in _WEAK_START_TOKENS:
        return 0.12
    if parts[-1] in _WEAK_END_TOKENS:
        return 0.18
    if len(parts) == 2 and parts[0] in _AUX_OR_GLUE and parts[1] in _AUX_OR_GLUE:
        return 0.08
    if len(parts) == 2 and parts[0] in _AUX_OR_GLUE:
        return 0.22
    if len(parts) == 2 and parts[1] in _AUX_OR_GLUE and parts[0] not in _WEAK_START_TOKENS:
        return 0.55
    if len(parts) >= 2 and all(len(p) <= 4 for p in parts):
        return 0.35
    return 1.0


def _known_phrase_boost(phrase: str) -> float:
    if phrase in KNOWN_PHRASES_SET:
        return 1.45
    for known in KNOWN_PHRASES:
        if known in phrase or phrase in known:
            return 1.25
    return 1.0


def _adjusted_label_score(phrase: str, pmi_score: float) -> float:
    quality = phrase_label_quality(phrase)
    if quality < 0.25:
        return 0.0
    return pmi_score * quality * _known_phrase_boost(phrase)


def _content_word_bonus(phrase: str) -> float:
    """Prefer substantive single-word anchors (governor, hacker, executive)."""
    parts = phrase.split()
    if len(parts) != 1:
        return 0.0
    word = parts[0]
    if len(word) >= 7:
        return 0.35
    if len(word) >= 5:
        return 0.2
    return 0.0


def _known_phrase_counts(texts: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        lowered = (text or "").lower()
        for phrase in KNOWN_PHRASES:
            if phrase in lowered:
                counts[phrase] += lowered.count(phrase)
    return counts


def _ngram_counts(texts: list[str], n: int) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        tokens = tokenize(text)
        for i in range(len(tokens) - n + 1):
            gram_tokens = tokens[i : i + n]
            if not all(is_meaningful_token(t) for t in gram_tokens):
                continue
            phrase = " ".join(gram_tokens)
            counts[phrase] += 1
    return counts


def _corpus_unigram_rates(all_texts: list[str]) -> dict[str, float]:
    counts: Counter[str] = Counter()
    total = 0
    for text in all_texts:
        for token in tokenize(text):
            counts[token] += 1
            total += 1
    if total <= 0:
        return {}
    return {word: count / total for word, count in counts.items()}


def _pmi_phrase_scores(
    member_texts: list[str],
    contrast_texts: list[str],
    *,
    min_count: int = 2,
) -> list[tuple[str, float]]:
    """Score bigrams/trigrams + known phrases by PMI vs contrast corpus."""
    member_n = max(sum(len(tokenize(t)) for t in member_texts), 1)
    contrast_n = max(sum(len(tokenize(t)) for t in contrast_texts), 1)

    phrase_counts: Counter[str] = Counter()
    phrase_counts.update(_known_phrase_counts(member_texts))
    phrase_counts.update(_ngram_counts(member_texts, 2))
    phrase_counts.update(_ngram_counts(member_texts, 3))

    contrast_counts: Counter[str] = Counter()
    contrast_counts.update(_known_phrase_counts(contrast_texts))
    contrast_counts.update(_ngram_counts(contrast_texts, 2))
    contrast_counts.update(_ngram_counts(contrast_texts, 3))

    corpus_rates = _corpus_unigram_rates(contrast_texts or member_texts)

    scored: list[tuple[str, float]] = []
    for phrase, count in phrase_counts.items():
        if count < min_count and " " not in phrase:
            continue
        if count < 1:
            continue
        # Skip phrases where every token is individually generic in corpus
        parts = phrase.split()
        if len(parts) == 1 and not is_meaningful_token(parts[0]):
            continue

        p_phrase = count / max(member_n, 1)
        contrast_count = contrast_counts.get(phrase, 0)
        p_contrast = (contrast_count + 0.5) / (contrast_n + 1.0)

        if len(parts) == 1:
            p_contrast = max(p_contrast, corpus_rates.get(parts[0], 1.0 / contrast_n))

        pmi = math.log2((p_phrase + 1e-9) / (p_contrast + 1e-9))
        if pmi < 1.0 and " " not in phrase:
            continue
        if pmi < 0.65 and " " in phrase and phrase not in KNOWN_PHRASES_SET:
            continue
        score = pmi * math.log1p(count)
        scored.append((phrase, score))

    scored.sort(
        key=lambda item: (_adjusted_label_score(item[0], item[1]), (" " in item[0])),
        reverse=True,
    )
    return scored


def rank_theme_labels(
    member_texts: list[str],
    contrast_texts: list[str],
    *,
    top_n: int = 6,
) -> tuple[list[str], list[str], float]:
    """
    Pick a theme anchor (unigram or phrase) plus supporting terms.

    Returns (theme_terms, quality_phrases, distinctiveness).
    theme_terms[0] is the best primary label for the cluster.
    """
    scored = _pmi_phrase_scores(member_texts, contrast_texts)
    unigram_scored = _pmi_phrase_scores(member_texts, contrast_texts, min_count=1)

    ranked: list[tuple[str, float]] = []
    seen: set[str] = set()
    for phrase, raw_score in scored + unigram_scored:
        if phrase in seen:
            continue
        adj = _adjusted_label_score(phrase, raw_score) + _content_word_bonus(phrase)
        if adj <= 0.0:
            continue
        ranked.append((phrase, adj))
        seen.add(phrase)
    ranked.sort(key=lambda item: item[1], reverse=True)

    theme_terms: list[str] = []
    quality_phrases: list[str] = []
    used_tokens: set[str] = set()

    for phrase, _score in ranked:
        parts = phrase.split()
        if any(p in used_tokens for p in parts):
            continue
        if " " in phrase and phrase_label_quality(phrase) >= 0.55:
            quality_phrases.append(phrase)
        if len(theme_terms) < top_n:
            theme_terms.append(phrase)
        used_tokens.update(parts)
        if len(theme_terms) >= top_n and len(quality_phrases) >= min(3, top_n // 2):
            break

    if not theme_terms:
        fallback = label_terms(member_texts, top_n=top_n)
        theme_terms = fallback
        if not quality_phrases:
            quality_phrases = [p for p in fallback if " " in p]

    distinctiveness = 0.0
    if ranked:
        top_scores = [s for _, s in ranked[:3]]
        distinctiveness = round(min(1.0, sum(top_scores) / max(len(top_scores), 1) / 6.0), 4)

    return theme_terms[:top_n], quality_phrases[:top_n], distinctiveness


def score_distinct_phrases(
    member_texts: list[str],
    contrast_texts: list[str],
    *,
    top_n: int = 6,
) -> tuple[list[str], list[str], float]:
    """
    Return (display_labels, fallback_unigrams, distinctiveness).

    display_labels[0] is the theme anchor (unigram or known phrase); weak PMI fragments
    are filtered out in favor of substantive terms like governor or election fraud.
    """
    theme_terms, quality_phrases, distinctiveness = rank_theme_labels(
        member_texts,
        contrast_texts,
        top_n=top_n,
    )
    display: list[str] = []
    seen: set[str] = set()
    for label in theme_terms:
        if label in seen:
            continue
        display.append(label)
        seen.add(label)
    for phrase in quality_phrases:
        if phrase in seen:
            continue
        display.append(phrase)
        seen.add(phrase)

    fallback = [t for t in theme_terms if " " not in t][:top_n]
    return display[:top_n], fallback[:top_n], distinctiveness


def assign_distinct_phrase_labels(
    cluster_texts: dict[int, list[str]],
    all_texts: list[str],
    *,
    top_n: int = 6,
) -> dict[int, tuple[list[str], list[str], float]]:
    """Pick distinctive phrase labels per cluster; reserve phrases for strongest clusters."""
    cluster_scores: dict[int, list[tuple[str, float]]] = {}
    for cluster_id, texts in cluster_texts.items():
        contrast = [
            line
            for other_id, other_texts in cluster_texts.items()
            if other_id != cluster_id
            for line in other_texts
        ]
        if not contrast:
            contrast = [t for t in all_texts if t not in texts] or all_texts
        cluster_scores[cluster_id] = _pmi_phrase_scores(texts, contrast)

    order = sorted(
        cluster_scores.keys(),
        key=lambda cid: cluster_scores[cid][0][1] if cluster_scores[cid] else 0.0,
        reverse=True,
    )

    claimed_phrases: set[str] = set()
    claimed_tokens: set[str] = set()
    labels: dict[int, tuple[list[str], list[str], float]] = {}

    for cluster_id in order:
        texts = cluster_texts[cluster_id]
        contrast = [
            line
            for other_id, other_texts in cluster_texts.items()
            if other_id != cluster_id
            for line in other_texts
        ]
        if not contrast:
            contrast = [t for t in all_texts if t not in texts] or all_texts

        phrases, fallback, distinctiveness = score_distinct_phrases(
            texts,
            contrast,
            top_n=top_n,
        )
        theme_terms, quality_phrases, _ = rank_theme_labels(texts, contrast, top_n=top_n)

        filtered: list[str] = []
        filtered_phrases: list[str] = []
        for label in theme_terms:
            parts = label.split()
            if label in claimed_phrases:
                continue
            if any(p in claimed_tokens for p in parts):
                continue
            filtered.append(label)
            claimed_phrases.add(label)
            claimed_tokens.update(parts)
            if " " in label and phrase_label_quality(label) >= 0.55:
                filtered_phrases.append(label)

        for phrase in quality_phrases:
            if phrase in filtered_phrases or phrase in claimed_phrases:
                continue
            parts = phrase.split()
            if any(p in claimed_tokens for p in parts):
                continue
            filtered_phrases.append(phrase)
            claimed_phrases.add(phrase)
            claimed_tokens.update(parts)

        if len(filtered) < 2:
            for phrase, _ in cluster_scores[cluster_id]:
                if phrase in filtered or phrase in claimed_phrases:
                    continue
                if phrase_label_quality(phrase) < 0.25:
                    continue
                filtered.append(phrase)
                claimed_phrases.add(phrase)
                claimed_tokens.update(phrase.split())
                if len(filtered) >= top_n:
                    break

        if not filtered:
            filtered = [w for w, _ in _pmi_phrase_scores(texts, contrast, min_count=1)][:top_n]
            filtered = [w for w in filtered if phrase_label_quality(w) >= 0.25]

        if not filtered_phrases:
            filtered_phrases = [p for p in filtered if " " in p and phrase_label_quality(p) >= 0.55]

        labels[cluster_id] = (filtered[:top_n], filtered_phrases[:top_n], distinctiveness)

    return labels


def label_terms(texts: list[str], *, top_n: int = 6) -> list[str]:
    """Backward-compatible unigram labels with filler filtering."""
    counts: Counter[str] = Counter()
    for text in texts:
        for word in tokenize(text):
            counts[word] += 1
    return [word for word, _ in counts.most_common(top_n)]
