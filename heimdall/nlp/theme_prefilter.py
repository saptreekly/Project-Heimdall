"""Pre-cluster hygiene: bucket spam, promo, and off-narrative posts before theme clustering."""

from __future__ import annotations

import re
from enum import Enum

from heimdall.nlp.market_chatter import is_market_chatter_post, market_chatter_score

_URL_RE = re.compile(r"https?://|www\.", re.I)
_PROMO_RE = re.compile(
    r"\b(?:follow(?:\s+me)?|subscribe|sign\s*up|promo|giveaway|dm\s+me|link\s+in\s+bio)\b",
    re.I,
)
_ASCII_WORD_RE = re.compile(r"[a-zA-Z]{3,}")
_NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")

PROMO_CLUSTER_ID = -3
SHORT_CLUSTER_ID = -4
NON_ENGLISH_CLUSTER_ID = -5
OFF_TOPIC_CLUSTER_ID = -6

MIN_CLUSTERABLE_CHARS = 24
OFF_TOPIC_KEYWORD_MIN_HITS = 1


class PrefilterReason(str, Enum):
    MARKET = "market"
    PROMO = "promo"
    SHORT = "short"
    NON_ENGLISH = "non_english"
    OFF_TOPIC = "off_topic"
    NARRATIVE = "narrative"


def is_promo_post(text: str) -> bool:
    raw = text or ""
    if _PROMO_RE.search(raw):
        return True
    urls = len(_URL_RE.findall(raw))
    words = len(raw.split())
    return urls >= 2 and words <= 12


def is_ultra_short_post(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < MIN_CLUSTERABLE_CHARS:
        return True
    alpha = sum(1 for ch in stripped if ch.isalpha())
    return alpha < 8


def is_non_english_post(text: str) -> bool:
    raw = text or ""
    if not raw.strip():
        return True
    ascii_words = _ASCII_WORD_RE.findall(raw)
    if len(ascii_words) >= 4:
        return False
    non_ascii = len(_NON_ASCII_RE.findall(raw))
    return non_ascii >= 3 or (len(ascii_words) <= 1 and len(raw) > 20)


def narrative_keyword_hits(text: str, keywords: list[str]) -> int:
    lowered = (text or "").lower()
    hits = 0
    for kw in keywords:
        term = kw.strip().lower()
        if term and term in lowered:
            hits += 1
    return hits


def is_off_topic_post(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return False
    return narrative_keyword_hits(text, keywords) < OFF_TOPIC_KEYWORD_MIN_HITS


def classify_post_for_clustering(
    text: str,
    *,
    narrative_keywords: list[str] | None = None,
) -> PrefilterReason:
    """Return why a post is excluded from narrative clustering (or NARRATIVE if eligible)."""
    if is_market_chatter_post(text):
        return PrefilterReason.MARKET
    if is_promo_post(text):
        return PrefilterReason.PROMO
    if is_ultra_short_post(text):
        return PrefilterReason.SHORT
    if is_non_english_post(text):
        return PrefilterReason.NON_ENGLISH
    if narrative_keywords and is_off_topic_post(text, narrative_keywords):
        return PrefilterReason.OFF_TOPIC
    return PrefilterReason.NARRATIVE


def prefilter_cluster_id(reason: PrefilterReason) -> int | None:
    return {
        PrefilterReason.PROMO: PROMO_CLUSTER_ID,
        PrefilterReason.SHORT: SHORT_CLUSTER_ID,
        PrefilterReason.NON_ENGLISH: NON_ENGLISH_CLUSTER_ID,
        PrefilterReason.OFF_TOPIC: OFF_TOPIC_CLUSTER_ID,
    }.get(reason)
