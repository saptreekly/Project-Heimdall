import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from heimdall.db.models import Base
from heimdall.db.models import Platform
from heimdall.export.dashboard_snapshot import build_dashboard_snapshot
from heimdall.ingestion.pipeline import IngestionPipeline


@pytest.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        pipeline = IngestionPipeline(session, platform=Platform.MOCK)
        await pipeline.ingest_narrative("snap_test", ["border"], limit=15)
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_dashboard_snapshot(db_session: AsyncSession) -> None:
    snap = await build_dashboard_snapshot(db_session)
    assert snap["version"] == 1
    assert len(snap["narratives"]) == 1
    nid = str(snap["narratives"][0]["id"])
    bundle = snap["by_narrative_id"][nid]
    assert len(bundle["posts"]) > 0
    assert "suspicion_score" in bundle["cib"]
    assert "authors" in bundle["graph"]
    assert "edges" in bundle["graph"]
    json.dumps(snap)
