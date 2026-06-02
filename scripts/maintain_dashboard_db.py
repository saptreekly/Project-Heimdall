#!/usr/bin/env python3
"""Weekly SQLite maintenance: orphans, dedupe audit, narrative guard, VACUUM."""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "dashboard" / "heimdall.db"
DEFAULT_KEEP = ("midterms_2026",)


@dataclass
class MaintenanceReport:
    db_path: Path
    size_before_kb: int = 0
    size_after_kb: int = 0
    orphan_scores_removed: int = 0
    orphan_edges_removed: int = 0
    orphan_narrative_edges_removed: int = 0
    duplicate_post_keys: list[tuple[int, str, str]] = field(default_factory=list)
    narratives_pruned: list[str] = field(default_factory=list)
    vacuumed: bool = False
    notes: list[str] = field(default_factory=list)


def _configure_db(db_path: Path) -> None:
    import os

    if not db_path.is_file():
        raise SystemExit(f"Missing database: {db_path}")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.resolve()}"


async def _remove_orphans() -> tuple[int, int, int]:
    from sqlalchemy import delete, select

    from heimdall.db.models import InteractionEdge, Narrative, OutrageScore, Post
    from heimdall.db.session import get_session_factory, init_db

    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        post_ids = set((await db.scalars(select(Post.id))).all())
        narrative_ids = set((await db.scalars(select(Narrative.id))).all())

        score_rows = (await db.execute(select(OutrageScore.id, OutrageScore.post_id))).all()
        orphan_scores = [sid for sid, pid in score_rows if pid not in post_ids]
        if orphan_scores:
            await db.execute(delete(OutrageScore).where(OutrageScore.id.in_(orphan_scores)))

        edge_rows = (
            await db.execute(
                select(InteractionEdge.id, InteractionEdge.source_post_id, InteractionEdge.narrative_id)
            )
        ).all()
        orphan_edge_ids = [
            eid
            for eid, source_id, narrative_id in edge_rows
            if source_id not in post_ids or narrative_id not in narrative_ids
        ]
        if orphan_edge_ids:
            await db.execute(delete(InteractionEdge).where(InteractionEdge.id.in_(orphan_edge_ids)))

        bad_narrative_edges = [
            eid for eid, _, narrative_id in edge_rows if narrative_id not in narrative_ids
        ]
        await db.commit()
        return len(orphan_scores), len(orphan_edge_ids), len(bad_narrative_edges)


async def _find_duplicate_keys() -> list[tuple[int, str, str]]:
    from sqlalchemy import func, select

    from heimdall.db.models import Post
    from heimdall.db.session import get_session_factory, init_db

    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        rows = (
            await db.execute(
                select(Post.narrative_id, Post.platform, Post.external_id, func.count())
                .group_by(Post.narrative_id, Post.platform, Post.external_id)
                .having(func.count() > 1)
            )
        ).all()
        return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]


async def _prune_narratives(keep: tuple[str, ...]) -> list[str]:
    from sqlalchemy import delete, select

    from heimdall.db.models import InteractionEdge, Narrative, OutrageScore, Post
    from heimdall.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        rows = (await db.execute(select(Narrative.id, Narrative.name))).all()
        keep_set = set(keep)
        remove_ids = [nid for nid, name in rows if name not in keep_set]
        if not remove_ids:
            return []

        remove_names = [name for nid, name in rows if nid in remove_ids]
        post_ids = (await db.scalars(select(Post.id).where(Post.narrative_id.in_(remove_ids)))).all()
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
        return remove_names


def _vacuum(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()


async def run_maintenance(
    db_path: Path,
    *,
    keep_narratives: tuple[str, ...] | None = None,
    vacuum: bool = True,
) -> MaintenanceReport:
    report = MaintenanceReport(db_path=db_path, size_before_kb=db_path.stat().st_size // 1024)
    _configure_db(db_path)

    scores, edges, _ = await _remove_orphans()
    report.orphan_scores_removed = scores
    report.orphan_edges_removed = edges

    report.duplicate_post_keys = await _find_duplicate_keys()
    if report.duplicate_post_keys:
        report.notes.append(
            f"Found {len(report.duplicate_post_keys)} duplicate post key(s) — unique index should prevent new dupes."
        )

    if keep_narratives:
        report.narratives_pruned = await _prune_narratives(keep_narratives)

    if vacuum:
        _vacuum(db_path)
        report.vacuumed = True

    report.size_after_kb = db_path.stat().st_size // 1024
    return report


def markdown_report(report: MaintenanceReport) -> str:
    lines = [
        "### Database maintenance",
        "",
        f"- **Path:** `{report.db_path}`",
        f"- **Size:** {report.size_before_kb} KB → {report.size_after_kb} KB",
        f"- **Orphan scores removed:** {report.orphan_scores_removed}",
        f"- **Orphan edges removed:** {report.orphan_edges_removed}",
        f"- **VACUUM:** {'yes' if report.vacuumed else 'no'}",
    ]
    if report.narratives_pruned:
        lines.append(f"- **Narratives pruned:** {', '.join(report.narratives_pruned)}")
    if report.duplicate_post_keys:
        lines.append(f"- **Duplicate keys (audit):** {len(report.duplicate_post_keys)}")
    for note in report.notes:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--keep",
        nargs="+",
        default=list(DEFAULT_KEEP),
        help="Prune narratives not in this list (pass --no-prune to skip).",
    )
    parser.add_argument("--no-prune", action="store_true")
    parser.add_argument("--no-vacuum", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    keep = None if args.no_prune else tuple(args.keep)
    report = asyncio.run(
        run_maintenance(args.db, keep_narratives=keep, vacuum=not args.no_vacuum)
    )
    if args.markdown:
        print(markdown_report(report))
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
