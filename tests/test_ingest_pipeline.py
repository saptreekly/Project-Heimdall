import pytest
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from heimdall.db.models import Base, Narrative, Platform, Post
from heimdall.ingestion.pipeline import IngestionPipeline
from heimdall.ingestion.schemas import RawPost


@pytest.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_ensure_narrative_syncs_keywords(db_session: AsyncSession) -> None:
    narrative = Narrative(name="sync_test", keywords="old")
    db_session.add(narrative)
    await db_session.flush()

    pipeline = IngestionPipeline(db_session)
    updated = await pipeline.ensure_narrative("sync_test", ["new", "keywords"])
    assert updated.keywords == "new,keywords"


@pytest.mark.asyncio
async def test_upsert_updates_existing_post(db_session: AsyncSession) -> None:
    narrative = Narrative(name="upsert_test", keywords="kw")
    db_session.add(narrative)
    await db_session.flush()

    raw = RawPost(
        platform=Platform.MOCK,
        external_id="ext-1",
        author_id="a1",
        text="original text",
        posted_at=datetime.now(timezone.utc),
        source_keyword="alpha",
    )
    pipeline = IngestionPipeline(db_session, platform=Platform.MOCK)
    action, post_id = await pipeline._upsert_post(narrative.id, raw)
    assert action == "inserted"
    assert post_id is not None

    raw2 = RawPost(
        platform=Platform.MOCK,
        external_id="ext-1",
        author_id="a1",
        text="updated text",
        posted_at=datetime.now(timezone.utc),
        source_keyword="beta",
    )
    action2, post_id2 = await pipeline._upsert_post(narrative.id, raw2)
    assert action2 == "updated"
    assert post_id2 == post_id

    row = await db_session.get(Post, post_id)
    assert row is not None
    assert row.text == "updated text"
    assert row.ingest_keyword == "beta"
