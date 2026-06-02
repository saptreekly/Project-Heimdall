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
        if pmi < 0.5 and " " in phrase:
            continue
        score = pmi * math.log1p(count)
        scored.append((phrase, score))

    scored.sort(key=lambda item: ((" " in item[0]), item[1]), reverse=True)
    return scored


def score_distinct_phrases(
    member_texts: list[str],
    contrast_texts: list[str],
    *,
    top_n: int = 6,
) -> tuple[list[str], list[str], float]:
    """
    Return (phrases, fallback_unigrams, distinctiveness).

    Phrases prefer multi-word frames like 'red wave' over separate 'red' + 'wave'.
    """
    scored = _pmi_phrase_scores(member_texts, contrast_texts)
    phrases: list[str] = []
    used_tokens: set[str] = set()

    for phrase, score in scored:
        if phrase in phrases:
            continue
        parts = phrase.split()
        if any(p in used_tokens for p in parts):
            continue
        phrases.append(phrase)
        used_tokens.update(parts)
        if len(phrases) >= top_n:
            break

    unigram_scored = _pmi_phrase_scores(
        member_texts,
        contrast_texts,
        min_count=1,
    )
    fallback = [p for p, _ in unigram_scored if " " not in p][:top_n]

    if not phrases and fallback:
        phrases = fallback[: min(3, top_n)]

    distinctiveness = 0.0
    if scored:
        top_scores = [s for _, s in scored[:3]]
        distinctiveness = round(min(1.0, sum(top_scores) / max(len(top_scores), 1) / 6.0), 4)

    return phrases[:top_n], fallback[:top_n], distinctiveness


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

        filtered: list[str] = []
        for phrase in phrases:
            parts = phrase.split()
            if phrase in claimed_phrases:
                continue
            if any(p in claimed_tokens for p in parts):
                continue
            filtered.append(phrase)
            claimed_phrases.add(phrase)
            claimed_tokens.update(parts)

        if len(filtered) < 2:
            for phrase, _ in cluster_scores[cluster_id]:
                if phrase in filtered or phrase in claimed_phrases:
                    continue
                filtered.append(phrase)
                claimed_phrases.add(phrase)
                claimed_tokens.update(phrase.split())
                if len(filtered) >= top_n:
                    break

        if not filtered:
            filtered = [w for w, _ in _pmi_phrase_scores(texts, contrast, min_count=1)][:top_n]

        labels[cluster_id] = (filtered[:top_n], fallback[:top_n], distinctiveness)

    return labels


def label_terms(texts: list[str], *, top_n: int = 6) -> list[str]:
    """Backward-compatible unigram labels with filler filtering."""
    counts: Counter[str] = Counter()
    for text in texts:
        for word in tokenize(text):
            counts[word] += 1
    return [word for word, _ in counts.most_common(top_n)]
