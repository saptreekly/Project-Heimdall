#!/usr/bin/env python3
"""Seed the dashboard database with mock ingest when no narratives exist (CI fallback)."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select


async def run() -> int:
    from heimdall.db.models import Narrative, Platform
    from heimdall.db.session import get_session_factory, init_db
    from heimdall.ingestion.pipeline import IngestionPipeline

    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        count = await db.scalar(select(func.count()).select_from(Narrative)) or 0
        if count > 0:
            print(f"Database already has {count} narrative(s); skipping seed.")
            return 0

        pipeline = IngestionPipeline(db, platform=Platform.MOCK)
        result = await pipeline.ingest_narrative(
            "demo_cib",
            ["border crisis", "election fraud"],
            limit=40,
        )
        await db.commit()
        print(
            f"Seeded mock narrative id={result['narrative_id']} "
            f"(posts={result['inserted']}, edges={result['edges']})"
        )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
