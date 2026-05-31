"""One-time style migrations for dev Postgres DBs created with native enums."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def migrate_postgres_enums_to_varchar(conn: AsyncConnection) -> None:
    """
    Early Heimdall used PostgreSQL native ENUMs (MOCK, REDDIT, …).
    App enums use lowercase string values (mock, reddit, …). Convert columns to VARCHAR.
    """
    result = await conn.execute(
        text(
            """
            SELECT udt_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'posts' AND column_name = 'platform'
            """
        )
    )
    row = result.first()
    if not row or row[0] != "platform":
        return

    await conn.execute(
        text(
            """
            ALTER TABLE posts
            ALTER COLUMN platform TYPE VARCHAR(32)
            USING (lower(platform::text))
            """
        )
    )
    await conn.execute(
        text(
            """
            ALTER TABLE interaction_edges
            ALTER COLUMN interaction_type TYPE VARCHAR(32)
            USING (lower(interaction_type::text))
            """
        )
    )
    await conn.execute(text("DROP TYPE IF EXISTS platform"))
    await conn.execute(text("DROP TYPE IF EXISTS interactiontype"))


async def migrate_posts_unique_per_narrative(conn: AsyncConnection) -> None:
    """Allow the same external post id under different narratives."""
    dialect = conn.dialect.name
    if dialect == "postgresql":
        await conn.execute(text("DROP INDEX IF EXISTS ix_posts_platform_external_id"))
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_posts_narrative_platform_external "
                "ON posts (narrative_id, platform, external_id)"
            )
        )
    elif dialect == "sqlite":
        await conn.execute(text("DROP INDEX IF EXISTS ix_posts_platform_external_id"))
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_posts_narrative_platform_external "
                "ON posts (narrative_id, platform, external_id)"
            )
        )
