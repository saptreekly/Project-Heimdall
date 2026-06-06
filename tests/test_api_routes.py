import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from heimdall.db.models import Base
from heimdall.main import app


@pytest.fixture
async def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("AUTO_IMPORT_ASTROTURF", "false")
    monkeypatch.setenv("INGEST_API_KEY", "")
    monkeypatch.delenv("INGEST_API_KEY", raising=False)

    from heimdall.config import get_settings

    get_settings.cache_clear()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from heimdall import db as db_pkg

    db_pkg.session._engine = None
    db_pkg.session._session_factory = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await engine.dispose()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_health(api_client: AsyncClient) -> None:
    res = await api_client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_narratives_empty(api_client: AsyncClient) -> None:
    res = await api_client.get("/api/v1/narratives")
    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.asyncio
async def test_mock_ingest(api_client: AsyncClient) -> None:
    res = await api_client.post(
        "/api/v1/ingest",
        json={
            "narrative_name": "api_test",
            "keywords": ["border"],
            "limit": 5,
            "platform": "mock",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["inserted"] >= 0
    assert "narrative_id" in body

    narratives = await api_client.get("/api/v1/narratives")
    names = [n["name"] for n in narratives.json()]
    assert "api_test" in names


@pytest.mark.asyncio
async def test_narrative_not_found(api_client: AsyncClient) -> None:
    res = await api_client.get("/api/v1/narratives/9999/posts")
    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.asyncio
async def test_ingest_api_key_required(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    db_path = tmp_path / "auth.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("AUTO_IMPORT_ASTROTURF", "false")
    monkeypatch.setenv("INGEST_API_KEY", "secret-key")

    from heimdall.config import get_settings

    get_settings.cache_clear()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from heimdall import db as db_pkg

    db_pkg.session._engine = None
    db_pkg.session._session_factory = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/api/v1/ingest",
            json={
                "narrative_name": "locked",
                "keywords": ["x"],
                "limit": 1,
                "platform": "mock",
            },
        )
        assert denied.status_code == 401

        allowed = await client.post(
            "/api/v1/ingest",
            json={
                "narrative_name": "locked",
                "keywords": ["x"],
                "limit": 1,
                "platform": "mock",
            },
            headers={"X-API-Key": "secret-key"},
        )
        assert allowed.status_code == 200

    await engine.dispose()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_astroturf_stats(api_client: AsyncClient) -> None:
    res = await api_client.get("/api/v1/datasets/astroturf/stats")
    assert res.status_code == 200
    assert "total_known_bots" in res.json()
