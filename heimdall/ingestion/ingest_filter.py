"""Ingest-time quality gates before posts are persisted."""

from __future__ import annotations

from dataclasses import dataclass

from heimdall.nlp.market_chatter import is_market_chatter_post
from heimdall.nlp.theme_prefilter import (
    PrefilterReason,
    classify_post_for_clustering,
    is_non_english_post,
    is_promo_post,
    is_ultra_short_post,
    narrative_keyword_hits,
)


@dataclass(frozen=True)
class IngestFilterResult:
    allow: bool
    reason: str | None = None


def should_ingest_post(
    text: str,
    *,
    narrative_keywords: list[str] | None = None,
    require_keyword_hit: bool = True,
) -> IngestFilterResult:
    if is_market_chatter_post(text):
        return IngestFilterResult(False, "market_chatter")
    if is_promo_post(text):
        return IngestFilterResult(False, "promo")
    if is_ultra_short_post(text):
        return IngestFilterResult(False, "short")
    if is_non_english_post(text):
        return IngestFilterResult(False, "non_english")

    if narrative_keywords and require_keyword_hit:
        keyword_hits = narrative_keyword_hits(text, narrative_keywords)
        off_topic = classify_post_for_clustering(text, narrative_keywords=narrative_keywords)
        if off_topic == PrefilterReason.OFF_TOPIC and keyword_hits < 1:
            return IngestFilterResult(False, "off_topic")

    return IngestFilterResult(True)
