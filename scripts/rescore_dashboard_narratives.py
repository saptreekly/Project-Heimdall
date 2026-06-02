#!/usr/bin/env python3
"""Rescore all narratives in the dashboard DB (lexicon v2.3 + optional embed themes)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "dashboard" / "heimdall.db"


def _configure_db(db_path: Path) -> None:
    if not db_path.is_file():
        raise SystemExit(f"Missing database: {db_path}")
    os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.resolve()}")


async def rescore_all(*, if_stale: bool = False) -> dict:
    from sqlalchemy import func, select

    from heimdall.db.models import Narrative, OutrageScore, Post
    from heimdall.db.session import get_session_factory, init_db
    from heimdall.nlp.outrage import MODEL_VERSION, MODEL_VERSION_EMBED, build_outrage_analyzer

    await init_db()
    analyzer = build_outrage_analyzer()
    target_version = MODEL_VERSION_EMBED if analyzer.use_embeddings else MODEL_VERSION

    factory = get_session_factory()
    async with factory() as db:
        narrative_ids = list((await db.scalars(select(Narrative.id))).all())
        all_count = len(narrative_ids)
        if not narrative_ids:
            return {"narratives": 0, "rescored": 0, "skipped": 0, "target_version": target_version}

        if if_stale:
            stale_ids: list[int] = []
            for nid in narrative_ids:
                stale_count = await db.scalar(
                    select(func.count())
                    .select_from(OutrageScore)
                    .join(Post, Post.id == OutrageScore.post_id)
                    .where(Post.narrative_id == nid, OutrageScore.model_version != target_version)
                )
                unscored = await db.scalar(
                    select(func.count())
                    .select_from(Post)
                    .outerjoin(OutrageScore, OutrageScore.post_id == Post.id)
                    .where(Post.narrative_id == nid, OutrageScore.id.is_(None))
                )
                if (stale_count or 0) > 0 or (unscored or 0) > 0:
                    stale_ids.append(nid)
            narrative_ids = stale_ids

        results: list[dict] = []
        total_rescored = 0
        for nid in narrative_ids:
            summary = await analyzer.rescore_narrative(db, nid)
            results.append(summary)
            total_rescored += int(summary.get("rescored") or 0)

        return {
            "narratives": len(results),
            "rescored": total_rescored,
            "skipped": all_count - len(narrative_ids) if if_stale else 0,
            "target_version": target_version,
            "transformer_sentiment": bool(analyzer._sentiment_pipe),
            "embedding_themes": analyzer.use_embeddings,
            "details": results,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--if-stale",
        action="store_true",
        help="Only rescore narratives whose scores are not on the current model version.",
    )
    args = parser.parse_args()
    _configure_db(args.db)
    report = asyncio.run(rescore_all(if_stale=args.if_stale))
    print(json.dumps(report, indent=2))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if summary_path:
        lines = [
            "### Outrage rescore",
            "",
            f"- Narratives rescored: **{report['narratives']}**",
            f"- Posts rescored: **{report['rescored']}**",
            f"- Model: `{report['target_version']}`",
            f"- Embedding themes: {report.get('embedding_themes')}",
            f"- Transformer sentiment: {report.get('transformer_sentiment')}",
            "",
        ]
        Path(summary_path).write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
