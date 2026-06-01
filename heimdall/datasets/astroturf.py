from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.config import get_settings
from heimdall.db.models import KnownBotAccount

SOURCE = "iu_astroturf"
DEFAULT_PLATFORM = "x"


def _insert_stmt(table):
    url = get_settings().database_url
    if url.startswith("sqlite"):
        return sqlite_insert(table)
    return pg_insert(table)


def load_astroturf_tsv(path: Path | str) -> list[tuple[str, str]]:
    """Parse IU astroturf TSV: user_id<TAB>label."""
    path = Path(path)
    rows: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        user_id, label = parts[0].strip(), parts[1].strip()
        if user_id:
            rows.append((user_id, label))
    return rows


async def import_astroturf(
    session: AsyncSession,
    path: Path | str | None = None,
    *,
    platform: str = DEFAULT_PLATFORM,
) -> dict:
    settings = get_settings()
    tsv_path = Path(path or settings.astroturf_tsv_path)
    if not tsv_path.is_file():
        raise FileNotFoundError(f"Astroturf TSV not found: {tsv_path}")

    before = await count_known_bots(session, platform)
    rows = load_astroturf_tsv(tsv_path)
    for user_id, label in rows:
        stmt = (
            _insert_stmt(KnownBotAccount)
            .values(
                platform=platform,
                author_id=user_id,
                label=label,
                source=SOURCE,
            )
            .on_conflict_do_nothing(index_elements=["platform", "author_id"])
        )
        await session.execute(stmt)

    await session.commit()
    after = await count_known_bots(session, platform)
    return {
        "path": str(tsv_path.resolve()),
        "parsed": len(rows),
        "new_rows": after - before,
        "total_in_db": after,
        "platform": platform,
        "source": SOURCE,
    }


async def narrative_bot_overlap(session: AsyncSession, narrative_id: int) -> dict:
    """Match narrative authors against IU astroturf (Twitter/X only, not Mastodon numeric IDs)."""
    from sqlalchemy import String, cast

    from heimdall.db.models import Post

    result = await session.execute(
        select(Post.author_id, cast(Post.platform, String)).where(
            Post.narrative_id == narrative_id
        )
    )
    rows = result.all()
    author_ids = {r[0] for r in rows}
    platforms = sorted({(r[1] or "").lower() for r in rows})
    # IU astroturf is Twitter user IDs; Mastodon IDs are also numeric but a different namespace.
    x_author_ids = list({r[0] for r in rows if (r[1] or "").lower() == "x"})
    labels = await lookup_labels(session, x_author_ids, DEFAULT_PLATFORM)
    denom = len(x_author_ids) or 1
    note = (
        "No platform=x posts in this narrative; IU astroturf only applies to Twitter/X author IDs."
        if not x_author_ids
        else None
    )
    return {
        "authors_in_narrative": len(author_ids),
        "platforms": platforms,
        "x_authors_checked": len(x_author_ids),
        "known_political_bots": len(labels),
        "known_bot_ratio": round(len(labels) / denom, 4) if x_author_ids else 0.0,
        "labeled_accounts": [
            {"author_id": aid, "label": lab} for aid, lab in list(labels.items())[:25]
        ],
        "note": note,
    }


async def count_known_bots(session: AsyncSession, platform: str = DEFAULT_PLATFORM) -> int:
    result = await session.execute(
        select(KnownBotAccount.id).where(KnownBotAccount.platform == platform)
    )
    return len(result.all())


async def lookup_labels(
    session: AsyncSession,
    author_ids: list[str],
    platform: str = DEFAULT_PLATFORM,
) -> dict[str, str]:
    if not author_ids:
        return {}
    result = await session.execute(
        select(KnownBotAccount.author_id, KnownBotAccount.label).where(
            KnownBotAccount.platform == platform,
            KnownBotAccount.author_id.in_(author_ids),
        )
    )
    return {row[0]: row[1] for row in result.all()}
