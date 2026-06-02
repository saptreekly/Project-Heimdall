#!/usr/bin/env python3
"""Remove narratives (and their posts/edges/scores) except those on the keep list."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "dashboard" / "heimdall.db"
DEFAULT_KEEP = ("midterms_2026",)


def _configure_db(db_path: Path | None) -> None:
    import os

    if db_path is None:
        db_path = DEFAULT_DB
    if not db_path.is_file():
        raise SystemExit(f"Missing database: {db_path}")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.resolve()}"


async def run(keep: tuple[str, ...]) -> int:
    from sqlalchemy import delete, select

    from heimdall.db.models import InteractionEdge, Narrative, OutrageScore, Post
    from heimdall.db.session import get_session_factory, init_db

    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        rows = (await db.execute(select(Narrative.id, Narrative.name))).all()
        if not rows:
            print("No narratives in database.")
            return 0

        keep_set = set(keep)
        remove_ids = [nid for nid, name in rows if name not in keep_set]
        if not remove_ids:
            print(f"Nothing to prune; keeping {len(rows)} narrative(s): {[n for _, n in rows]}")
            return 0

        remove_names = [name for nid, name in rows if nid in remove_ids]
        post_ids = (
            await db.scalars(select(Post.id).where(Post.narrative_id.in_(remove_ids)))
        ).all()

        if post_ids:
            await db.execute(delete(OutrageScore).where(OutrageScore.post_id.in_(post_ids)))
            await db.execute(
                delete(InteractionEdge).where(
                    (InteractionEdge.narrative_id.in_(remove_ids))
                    | (InteractionEdge.source_post_id.in_(post_ids))
                    | (InteractionEdge.target_post_id.in_(post_ids))
                )
            )
            await db.execute(delete(Post).where(Post.id.in_(post_ids)))

        await db.execute(delete(Narrative).where(Narrative.id.in_(remove_ids)))
        await db.commit()

        kept = [name for _, name in rows if name in keep_set]
        print(f"Removed {len(remove_names)} narrative(s): {remove_names}")
        print(f"Kept: {kept}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"SQLite database path (default: {DEFAULT_DB.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--keep",
        nargs="+",
        default=list(DEFAULT_KEEP),
        help=f"Narrative names to retain (default: {', '.join(DEFAULT_KEEP)})",
    )
    args = parser.parse_args()
    _configure_db(args.db)
    raise SystemExit(asyncio.run(run(tuple(args.keep))))


if __name__ == "__main__":
    main()
