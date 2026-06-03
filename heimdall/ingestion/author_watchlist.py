"""Author frontier for snowball X ingest — poll watched accounts via from: search."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from heimdall.config import get_settings
from heimdall.ingestion.query_plan import QueryPlan, SearchQuery, build_author_poll_query


@dataclass
class WatchAuthor:
    author_id: str
    handle: str | None = None
    discovered_via: str = "keyword"
    depth: int = 0
    priority: float = 0.5
    last_polled_at: str | None = None
    last_tweet_at: str | None = None
    inserted_total: int = 0
    polls: int = 0
    inserts_from_polls: int = 0
    status: str = "active"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WatchAuthor:
        return cls(
            author_id=str(data["author_id"]),
            handle=data.get("handle"),
            discovered_via=str(data.get("discovered_via") or "keyword"),
            depth=int(data.get("depth") or 0),
            priority=float(data.get("priority") or 0.5),
            last_polled_at=data.get("last_polled_at"),
            last_tweet_at=data.get("last_tweet_at"),
            inserted_total=int(data.get("inserted_total") or 0),
            polls=int(data.get("polls") or 0),
            inserts_from_polls=int(data.get("inserts_from_polls") or 0),
            status=str(data.get("status") or "active"),
        )


@dataclass
class NarrativeWatchlist:
    authors: dict[str, WatchAuthor] = field(default_factory=dict)
    run_counter: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NarrativeWatchlist:
        authors = {
            aid: WatchAuthor.from_dict(row)
            for aid, row in (data.get("authors") or {}).items()
        }
        return cls(authors=authors, run_counter=int(data.get("run_counter") or 0))


@dataclass
class AuthorWatchlistStore:
    narratives: dict[str, NarrativeWatchlist] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> AuthorWatchlistStore:
        p = path or watchlist_path()
        if not p.is_file():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cls()
        narratives = {
            name: NarrativeWatchlist.from_dict(block)
            for name, block in (raw.get("narratives") or {}).items()
        }
        return cls(narratives=narratives)

    def save(self, path: Path | None = None) -> None:
        p = path or watchlist_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "narratives": {
                name: {
                    "run_counter": block.run_counter,
                    "authors": {aid: asdict(author) for aid, author in block.authors.items()},
                }
                for name, block in self.narratives.items()
            }
        }
        p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def narrative(self, name: str) -> NarrativeWatchlist:
        if name not in self.narratives:
            self.narratives[name] = NarrativeWatchlist()
        return self.narratives[name]


def watchlist_path() -> Path:
    return Path(get_settings().x_author_watchlist_path)


def _normalize_handle(handle: str | None) -> str | None:
    if not handle:
        return None
    token = handle.strip().lstrip("@")
    return token or None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _since_date_for_poll(author: WatchAuthor) -> str | None:
    if author.last_polled_at:
        polled = _parse_iso(author.last_polled_at)
        if polled:
            return polled.astimezone(UTC).date().isoformat()
    if author.last_tweet_at:
        seen = _parse_iso(author.last_tweet_at)
        if seen:
            return seen.astimezone(UTC).date().isoformat()
    return (date.today() - timedelta(days=7)).isoformat()


def context_terms_from_keywords(keywords: list[str], *, max_terms: int = 5) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        token = kw.strip()
        if not token or token.lower().startswith("list:"):
            continue
        if token.lower() in seen:
            continue
        seen.add(token.lower())
        out.append(token)
        if len(out) >= max_terms:
            break
    return out


def resolve_x_scheduled_mode(
    narrative_name: str,
    *,
    store: AuthorWatchlistStore | None = None,
) -> tuple[str, WatchAuthor | None, AuthorWatchlistStore]:
    """Return ('keyword' | 'author_poll', optional author, store). Bumps run_counter."""
    settings = get_settings()
    data = store or AuthorWatchlistStore.load()
    block = data.narrative(narrative_name)
    block.run_counter += 1
    mode = "keyword"
    author: WatchAuthor | None = None
    every = max(settings.x_author_poll_every_n, 1)
    if settings.x_author_poll_enabled and block.run_counter % every == 0:
        author = pick_author_for_poll(narrative_name, store=data)
        if author:
            mode = "author_poll"
    data.save()
    return mode, author, data


def pick_author_for_poll(
    narrative_name: str,
    *,
    store: AuthorWatchlistStore | None = None,
) -> WatchAuthor | None:
    settings = get_settings()
    data = store or AuthorWatchlistStore.load()
    block = data.narrative(narrative_name)
    max_depth = settings.x_author_max_depth
    candidates = [
        a
        for a in block.authors.values()
        if a.status == "active" and a.depth <= max_depth and _normalize_handle(a.handle)
    ]
    if not candidates:
        return None

    def sort_key(author: WatchAuthor) -> tuple:
        polled = _parse_iso(author.last_polled_at)
        never = polled is None
        stale = polled.timestamp() if polled else 0.0
        return (0 if never else 1, -author.priority, stale)

    candidates.sort(key=sort_key)
    return candidates[0]


def build_author_poll_plan(
    author: WatchAuthor,
    *,
    context_terms: list[str],
    limit: int,
    exclude_terms: tuple[str, ...],
) -> QueryPlan:
    handle = _normalize_handle(author.handle)
    if not handle:
        raise ValueError(f"Author {author.author_id} has no handle for polling")
    since = _since_date_for_poll(author)
    platform_query = build_author_poll_query(
        handle,
        context_terms=context_terms,
        exclude_terms=exclude_terms,
        since_date=since,
    )
    label = f"author:@{handle}"
    query = SearchQuery(
        narrative_keyword=label,
        platform_query=platform_query,
        query_type="author_poll",
        max_results=limit,
    )
    notes = [f"Author poll for @{handle} since {since or 'recent'}"]
    if context_terms:
        notes.append(f"Context OR terms: {', '.join(context_terms[:5])}")
    from heimdall.db.models import Platform

    return QueryPlan(
        Platform.X,
        [query],
        limit,
        keywords=[label],
        notes=notes,
    )


def register_author_discovery(
    narrative_name: str,
    *,
    author_id: str,
    handle: str | None,
    discovered_via: str,
    depth: int,
    inserted_delta: int = 0,
    poll_delta: int = 0,
    inserts_from_poll_delta: int = 0,
    store: AuthorWatchlistStore | None = None,
    bot_author_ids: set[str] | None = None,
) -> None:
    if not author_id or author_id == "unknown":
        return
    if bot_author_ids and author_id in bot_author_ids:
        return

    settings = get_settings()
    data = store or AuthorWatchlistStore.load()
    block = data.narrative(narrative_name)
    max_depth = settings.x_author_max_depth
    if depth > max_depth:
        return

    existing = block.authors.get(author_id)
    handle_norm = _normalize_handle(handle)
    priority_boost = min(inserted_delta, 5) * 0.12
    if existing:
        if handle_norm and not existing.handle:
            existing.handle = handle_norm
        existing.inserted_total += inserted_delta
        existing.polls += poll_delta
        existing.inserts_from_polls += inserts_from_poll_delta
        existing.priority = min(1.0, existing.priority + priority_boost)
        if existing.status == "pruned" and inserted_delta > 0:
            existing.status = "active"
    else:
        if len(block.authors) >= settings.x_author_watchlist_max:
            _evict_lowest_priority(block)
        block.authors[author_id] = WatchAuthor(
            author_id=author_id,
            handle=handle_norm,
            discovered_via=discovered_via,
            depth=depth,
            priority=0.45 + priority_boost,
            inserted_total=inserted_delta,
            polls=poll_delta,
            inserts_from_polls=inserts_from_poll_delta,
        )
    data.save()


def _evict_lowest_priority(block: NarrativeWatchlist) -> None:
    if not block.authors:
        return
    victim = min(block.authors.values(), key=lambda a: (a.priority, a.inserted_total))
    block.authors.pop(victim.author_id, None)


def record_author_poll_start(
    narrative_name: str,
    author: WatchAuthor,
    *,
    store: AuthorWatchlistStore | None = None,
) -> None:
    data = store or AuthorWatchlistStore.load()
    row = data.narrative(narrative_name).authors.get(author.author_id)
    if not row:
        return
    row.last_polled_at = datetime.now(UTC).isoformat()
    row.polls += 1
    data.save()


def record_author_poll_result(
    narrative_name: str,
    author_id: str,
    *,
    inserts: int,
    latest_post_at: str | None = None,
    store: AuthorWatchlistStore | None = None,
) -> None:
    data = store or AuthorWatchlistStore.load()
    row = data.narrative(narrative_name).authors.get(author_id)
    if not row:
        return
    row.inserts_from_polls += inserts
    row.inserted_total += inserts
    if inserts:
        row.priority = min(1.0, row.priority + min(inserts, 5) * 0.1)
    if latest_post_at:
        row.last_tweet_at = latest_post_at
    data.save()


def apply_pipeline_discoveries(
    narrative_name: str,
    discoveries: list[dict[str, Any]],
    *,
    bot_author_ids: set[str] | None = None,
    store: AuthorWatchlistStore | None = None,
) -> None:
    for row in discoveries:
        register_author_discovery(
            narrative_name,
            author_id=str(row.get("author_id") or ""),
            handle=row.get("handle"),
            discovered_via=str(row.get("discovered_via") or "keyword"),
            depth=int(row.get("depth") or 0),
            inserted_delta=int(row.get("inserted") or 0),
            store=store,
            bot_author_ids=bot_author_ids,
        )


def prune_stale_authors(
    narrative_name: str,
    *,
    min_polls: int = 2,
    max_inserts_from_polls: int = 0,
    store: AuthorWatchlistStore | None = None,
) -> list[str]:
    data = store or AuthorWatchlistStore.load()
    block = data.narrative(narrative_name)
    removed: list[str] = []
    for author_id, row in list(block.authors.items()):
        if row.status != "active":
            continue
        if row.polls >= min_polls and row.inserts_from_polls <= max_inserts_from_polls:
            row.status = "pruned"
            removed.append(author_id)
    if removed:
        data.save()
    return removed
