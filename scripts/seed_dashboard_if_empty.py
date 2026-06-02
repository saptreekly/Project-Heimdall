#!/usr/bin/env python3
"""No-op when the dashboard DB is empty — real data must come from scheduled X ingest."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select


async def run() -> int:
    from heimdall.db.models import Narrative
    from heimdall.db.session import get_session_factory, init_db

    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        count = await db.scalar(select(func.count()).select_from(Narrative)) or 0
        if count > 0:
            print(f"Database already has {count} narrative(s); skipping seed.")
            return 0

        print(
            "Database is empty — not seeding mock data. "
            "Run scheduled ingest or commit data/dashboard/heimdall.db.",
            file=sys.stderr,
        )
        return 1


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
