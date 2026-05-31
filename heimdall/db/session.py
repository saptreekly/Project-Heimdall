from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from heimdall.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().database_url
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_async_engine(url, echo=False, connect_args=connect_args)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


async def init_db() -> None:
    from heimdall.db.migrate import (
        migrate_postgres_enums_to_varchar,
        migrate_posts_unique_per_narrative,
    )
    from heimdall.db.models import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "postgresql":
            await migrate_postgres_enums_to_varchar(conn)
        await migrate_posts_unique_per_narrative(conn)

    await _maybe_import_astroturf()


async def _maybe_import_astroturf() -> None:
    from pathlib import Path

    from sqlalchemy import func, select

    from heimdall.config import get_settings
    from heimdall.datasets.astroturf import import_astroturf
    from heimdall.db.models import KnownBotAccount

    settings = get_settings()
    if not settings.auto_import_astroturf:
        return
    if not Path(settings.astroturf_tsv_path).is_file():
        return

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(func.count()).select_from(KnownBotAccount))
        if (result.scalar() or 0) > 0:
            return
        await import_astroturf(session, settings.astroturf_tsv_path)
