"""Ingest configuration passed from API / scheduled jobs into the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IngestOptions:
    x_exclude_terms: tuple[str, ...] = ()
    x_list_sources: tuple[str, ...] = ()
    reddit_subreddits: tuple[str, ...] = ("politics", "news", "Conservative")
    fallback_platforms: tuple[str, ...] = ()
    apply_ingest_filter: bool = True
    require_keyword_hit: bool = True
    backfill_reply_targets: bool = True
    backfill_max_targets: int = 5
    dry_run: bool = False
    query_plan_notes: list[str] = field(default_factory=list)
