from datetime import datetime

from pydantic import BaseModel, Field


class NarrativeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    keywords: list[str] = Field(..., min_length=1)


class IngestRequest(BaseModel):
    narrative_name: str
    keywords: list[str]
    limit: int = Field(default=50, ge=1, le=200)
    # Omit for DEFAULT_INGESTER (hackernews). Options: hackernews, mastodon, mock, reddit, tweet_eval
    platform: str | None = None


class Neo4jSyncResponse(BaseModel):
    narrative_id: int
    authors_written: int
    posts_written: int
    edges_written: int
    neo4j_browser: str
    sample_query: str
    cib: dict | None = None


class IngestResponse(BaseModel):
    narrative_id: int
    fetched: int
    inserted: int
    scored: int
    edges: int
    guardrails: dict | None = None


class PostOut(BaseModel):
    id: int
    platform: str
    author_id: str
    text: str
    posted_at: datetime
    outrage_index: float | None = None
    sentiment_label: str | None = None
    benchmark_label: str | None = None


class CIBResponse(BaseModel):
    narrative_id: int
    suspicion_score: float
    organic_score: float
    signals: list[str]
    node_count: int
    edge_count: int
    density: float
    top_amplifiers: list[dict]
    coordinated_clusters: list[dict]
    iu_astroturf: dict | None = None


class NarrativeSummary(BaseModel):
    id: int
    name: str
    keywords: str
    post_count: int


class DuplicateClusterOut(BaseModel):
    count: int
    author_count: int
    author_ids: list[str]
    post_ids: list[int]
    sample_text: str


class AstroturfImportResponse(BaseModel):
    path: str
    parsed: int
    new_rows: int
    total_in_db: int
    platform: str
    source: str
