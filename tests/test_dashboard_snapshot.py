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
    assert snap["version"] >= 1
    assert "cross_pollination" in snap
    assert "meta" in snap
    assert len(snap["narratives"]) == 1
    nid = str(snap["narratives"][0]["id"])
    bundle = snap["by_narrative_id"][nid]
    assert "near_duplicates" in bundle
    assert len(bundle["posts"]) > 0
    assert "suspicion_score" in bundle["cib"]
    assert "text_coordination_score" in bundle["cib"]
    assert "graph_suspicion_score" in bundle["cib"]
    assert "graph_sufficient" in bundle["cib"]
    assert "provenance" in bundle
    assert bundle["provenance"]["posts_total_db"] >= len(bundle["posts"])
    assert snap["version"] == 5
    assert "authors" in bundle["graph"]
    assert "edges" in bundle["graph"]
    assert "stats" in bundle["graph"]
    assert bundle["graph"]["stats"]["author_count"] >= 1
    assert "themes" in bundle
    assert "clusters" in bundle["themes"]
    assert bundle["themes"]["available"] is False
    json.dumps(snap)
