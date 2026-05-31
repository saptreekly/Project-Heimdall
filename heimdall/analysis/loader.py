"""Load persisted Heimdall rows into pandas for notebooks and scripts."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import pandas as pd
from sqlalchemy import create_engine, text

_DEFAULT_DB = "sqlite:///./heimdall.db"


def sync_database_url(url: str | None = None) -> str:
    """Convert async SQLAlchemy URL to a sync URL for pandas.read_sql."""
    raw = url or os.environ.get("DATABASE_URL", _DEFAULT_DB)
    return (
        raw.replace("sqlite+aiosqlite", "sqlite")
        .replace("postgresql+asyncpg", "postgresql+psycopg2")
    )


def load_narratives(database_url: str | None = None) -> pd.DataFrame:
    engine = create_engine(sync_database_url(database_url))
    query = text(
        """
        SELECT n.id, n.name, n.keywords, n.created_at,
               COUNT(p.id) AS post_count
        FROM narratives n
        LEFT JOIN posts p ON p.narrative_id = n.id
        GROUP BY n.id, n.name, n.keywords, n.created_at
        ORDER BY n.id
        """
    )
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def load_narrative_posts(
    *,
    narrative_id: int | None = None,
    narrative_name: str | None = None,
    database_url: str | None = None,
    min_outrage: float | None = None,
) -> pd.DataFrame:
    if narrative_id is None and narrative_name is None:
        raise ValueError("Provide narrative_id or narrative_name")

    engine = create_engine(sync_database_url(database_url))
    clauses = []
    params: dict = {}
    if narrative_id is not None:
        clauses.append("p.narrative_id = :narrative_id")
        params["narrative_id"] = narrative_id
    if narrative_name is not None:
        clauses.append("n.name = :narrative_name")
        params["narrative_name"] = narrative_name
    if min_outrage is not None:
        clauses.append("s.outrage_index >= :min_outrage")
        params["min_outrage"] = min_outrage

    where = " AND ".join(clauses)
    query = text(
        f"""
        SELECT
            p.id AS post_id,
            n.id AS narrative_id,
            n.name AS narrative_name,
            p.platform,
            p.external_id,
            p.author_id,
            p.author_handle,
            p.text,
            p.posted_at,
            p.created_at AS ingested_at,
            s.outrage_index,
            s.sentiment_label,
            s.dehumanization_score,
            s.anti_authority_score,
            s.conflict_escalation,
            s.model_version,
            kb.label AS known_bot_label
        FROM posts p
        JOIN narratives n ON n.id = p.narrative_id
        LEFT JOIN outrage_scores s ON s.post_id = p.id
        LEFT JOIN known_bot_accounts kb
            ON kb.platform = p.platform AND kb.author_id = p.author_id
        WHERE {where}
        ORDER BY p.posted_at DESC
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=params)
    if not df.empty and "posted_at" in df.columns:
        df["posted_at"] = pd.to_datetime(df["posted_at"], utc=True)
    return df


def db_path_hint(database_url: str | None = None) -> str:
    parsed = urlparse(sync_database_url(database_url).replace("sqlite:///", "file://"))
    if parsed.scheme == "file" or sync_database_url(database_url).startswith("sqlite"):
        path = sync_database_url(database_url).split("///", 1)[-1]
        return re.sub(r"^\./", "", path)
    return sync_database_url(database_url)
