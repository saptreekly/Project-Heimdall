"""Platform-specific search query planning from narrative keywords."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from heimdall.db.models import Platform

_LIST_PREFIX = "list:"
_TAG_RE = re.compile(r"[^a-z0-9_]+", re.I)
_DEFAULT_X_EXCLUDES = ("$SPX", "$VIX", "$NDX", "btc", "eth", "crypto", "mkt")


@dataclass(frozen=True)
class SearchQuery:
    narrative_keyword: str
    platform_query: str
    query_type: str
    max_results: int


@dataclass
class QueryPlan:
    platform: Platform
    queries: list[SearchQuery]
    total_limit: int
    keywords: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QueryPlanOptions:
    x_exclude_terms: tuple[str, ...] = _DEFAULT_X_EXCLUDES
    x_list_sources: tuple[str, ...] = ()
    reddit_subreddits: tuple[str, ...] = ("politics", "news", "Conservative")
    per_keyword_queries: bool = True


def _quote_phrase(keyword: str) -> str:
    token = keyword.strip()
    if not token:
        return token
    if token.lower().startswith(_LIST_PREFIX):
        return token
    if " " in token and not (token.startswith('"') and token.endswith('"')):
        return f'"{token}"'
    return token


def _x_exclude_clause(terms: tuple[str, ...]) -> str:
    cleaned = [t.strip() for t in terms if t.strip()]
    if not cleaned:
        return ""
    inner = " OR ".join(cleaned)
    return f"-({inner})"


def build_author_poll_query(
    handle: str,
    *,
    context_terms: list[str] | None = None,
    exclude_terms: tuple[str, ...] = _DEFAULT_X_EXCLUDES,
    since_date: str | None = None,
) -> str:
    """X search query polling a single account (from: + optional narrative OR + since)."""
    token = handle.strip().lstrip("@")
    if not token:
        raise ValueError("handle required for author poll query")
    parts: list[str] = [f"from:{token}"]
    terms = [t.strip() for t in (context_terms or []) if t.strip()]
    if terms:
        quoted = " OR ".join(_quote_phrase(t) for t in terms)
        parts.append(f"({quoted})")
    if since_date:
        parts.append(f"since:{since_date}")
    exclude = _x_exclude_clause(exclude_terms)
    if exclude:
        parts.append(exclude)
    return " ".join(parts)


def _mastodon_hashtags(keyword: str) -> list[str]:
    raw = keyword.strip().lower()
    if not raw:
        return []
    tags: list[str] = []
    first = _TAG_RE.sub("", raw.split()[0])
    if first:
        tags.append(first)
    compact = _TAG_RE.sub("", raw.replace(" ", ""))
    if compact and compact not in tags:
        tags.append(compact)
    underscored = _TAG_RE.sub("_", raw.replace(" ", "_"))
    if underscored and underscored not in tags:
        tags.append(underscored)
    return tags[:3]


def build_query_plan(
    platform: Platform,
    keywords: list[str],
    limit: int,
    *,
    options: QueryPlanOptions | None = None,
) -> QueryPlan:
    opts = options or QueryPlanOptions()
    cleaned = [k.strip() for k in keywords if k.strip()]
    if not cleaned:
        raise ValueError("At least one keyword is required")

    per_query = max(limit // max(len(cleaned), 1), 1)
    queries: list[SearchQuery] = []
    notes: list[str] = []

    if platform == Platform.X:
        exclude = _x_exclude_clause(opts.x_exclude_terms)
        if exclude:
            notes.append(f"X exclude clause: {exclude}")
        for source in opts.x_list_sources:
            if source.strip():
                queries.append(
                    SearchQuery(
                        narrative_keyword=source.strip(),
                        platform_query=source.strip(),
                        query_type="list",
                        max_results=per_query,
                    )
                )
        for keyword in cleaned:
            if keyword.lower().startswith(_LIST_PREFIX):
                queries.append(
                    SearchQuery(keyword, keyword, "list", per_query)
                )
                continue
            query = _quote_phrase(keyword)
            if exclude:
                query = f"{query} {exclude}"
            queries.append(
                SearchQuery(keyword, query, "search", per_query)
            )
        return QueryPlan(platform, queries, limit, keywords=cleaned, notes=notes)

    if platform == Platform.MASTODON:
        for keyword in cleaned:
            tags = _mastodon_hashtags(keyword)
            for tag in tags:
                queries.append(
                    SearchQuery(keyword, tag, "hashtag", max(per_query // max(len(tags), 1), 5))
                )
        notes.append("Mastodon uses multi-variant hashtags per keyword")
        return QueryPlan(platform, queries, limit, keywords=cleaned, notes=notes)

    if platform == Platform.REDDIT:
        fixed: list[SearchQuery] = []
        for keyword in cleaned:
            quoted = _quote_phrase(keyword)
            share = max(per_query // max(len(opts.reddit_subreddits), 1), 5)
            for subreddit in opts.reddit_subreddits:
                fixed.append(
                    SearchQuery(
                        keyword,
                        f"r/{subreddit}:{quoted}",
                        "subreddit",
                        share,
                    )
                )
        notes.append(f"Reddit subreddits: {', '.join(opts.reddit_subreddits)}")
        return QueryPlan(platform, fixed, limit, keywords=cleaned, notes=notes)

    if platform == Platform.HACKERNEWS:
        if opts.per_keyword_queries:
            for keyword in cleaned:
                queries.append(
                    SearchQuery(keyword, keyword, "search", per_query)
                )
        else:
            queries.append(
                SearchQuery(
                    " ".join(cleaned),
                    " ".join(cleaned),
                    "combined",
                    limit,
                )
            )
        return QueryPlan(platform, queries, limit, keywords=cleaned, notes=notes)

    # Mock / TweetEval / default
    for keyword in cleaned:
        queries.append(SearchQuery(keyword, keyword, "search", per_query))
    return QueryPlan(platform, queries, limit, keywords=cleaned, notes=notes)
