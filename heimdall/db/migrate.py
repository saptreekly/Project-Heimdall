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


async def _table_has_column(conn: AsyncConnection, table: str, column: str) -> bool:
    dialect = conn.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        return any(row[1] == column for row in result.fetchall())
    result = await conn.execute(
        text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    )
    return result.first() is not None


async def migrate_outrage_score_v23(conn: AsyncConnection) -> None:
    """Add polarity, component scores, and escalation tier columns."""
    additions = [
        ("polarity", "VARCHAR(16) DEFAULT 'neutral' NOT NULL"),
        ("escalation_tier", "VARCHAR(32) DEFAULT 'neutral' NOT NULL"),
        ("negativity_score", "FLOAT DEFAULT 0.0 NOT NULL"),
        ("ragebait_score", "FLOAT DEFAULT 0.0 NOT NULL"),
        ("stance_score", "FLOAT DEFAULT 0.0 NOT NULL"),
    ]
    for column, spec in additions:
        if await _table_has_column(conn, "outrage_scores", column):
            continue
        await conn.execute(text(f"ALTER TABLE outrage_scores ADD COLUMN {column} {spec}"))

    if not await _table_has_column(conn, "outrage_scores", "escalation_tier"):
        return

    await conn.execute(
        text(
            """
            UPDATE outrage_scores
            SET escalation_tier = CASE
                WHEN sentiment_label IN ('high_conflict', 'escalating', 'emerging_theme')
                    THEN sentiment_label
                ELSE 'neutral'
            END
            WHERE escalation_tier = 'neutral'
              AND sentiment_label IN ('high_conflict', 'escalating', 'emerging_theme')
            """
        )
    )
    await conn.execute(
        text(
            """
            UPDATE outrage_scores
            SET polarity = CASE
                WHEN sentiment_label = 'negative'
                    OR escalation_tier IN ('high_conflict', 'escalating', 'emerging_theme')
                    OR outrage_index >= 0.32
                    THEN 'negative'
                ELSE 'neutral'
            END
            WHERE polarity = 'neutral'
            """
        )
    )


async def migrate_post_embeddings(conn: AsyncConnection) -> None:
    """Create post_embeddings table on existing DBs (create_all handles fresh installs)."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS post_embeddings (
                    post_id INTEGER NOT NULL PRIMARY KEY,
                    model VARCHAR(64) NOT NULL,
                    dim INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY(post_id) REFERENCES posts (id)
                )
                """
            )
        )
        return

    result = await conn.execute(
        text(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'post_embeddings'
            """
        )
    )
    if result.first():
        return
    await conn.execute(
        text(
            """
            CREATE TABLE post_embeddings (
                post_id INTEGER NOT NULL PRIMARY KEY REFERENCES posts(id),
                model VARCHAR(64) NOT NULL,
                dim INTEGER NOT NULL,
                vector BYTEA NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
            )
            """
        )
    )
