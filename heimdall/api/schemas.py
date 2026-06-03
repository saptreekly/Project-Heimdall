from datetime import datetime

from pydantic import BaseModel, Field


class NarrativeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    keywords: list[str] = Field(..., min_length=1)


class IngestRequest(BaseModel):
    narrative_name: str
    keywords: list[str]
    limit: int = Field(default=50, ge=1, le=200)
    platform: str | None = None
    x_exclude_terms: list[str] = Field(default_factory=list)
    x_list_sources: list[str] = Field(default_factory=list)
    reddit_subreddits: list[str] = Field(default_factory=list)
    apply_ingest_filter: bool = True
    require_keyword_hit: bool = True


class IngestPreviewRequest(IngestRequest):
    sample_limit: int = Field(default=20, ge=1, le=50)


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
    updated: int = 0
    duplicates: int = 0
    filtered: int = 0
    net_new: int = 0
    duplicate_rate: float = 0.0
    processed: int = 0
    pages_fetched: int = 1
    second_page_triggered: bool = False
    rescored_total: int = 0
    keyword_stats: dict | None = None
    guardrails: dict | None = None


class PostOut(BaseModel):
    id: int
    platform: str
    external_id: str | None = None
    author_id: str
    author_handle: str | None = None
    text: str
    posted_at: datetime
    outrage_index: float | None = None
    sentiment_label: str | None = None
    polarity: str | None = None
    escalation_tier: str | None = None
    negativity_score: float | None = None
    ragebait_score: float | None = None
    stance_score: float | None = None
    dehumanization_score: float | None = None
    anti_authority_score: float | None = None
    conflict_escalation: float | None = None
    benchmark_label: str | None = None
    near_duplicate_group: int | None = None
    cross_author_fuzzy_cluster: int | None = None
    copypasta_score: float | None = None
    status_url: str | None = None


class CIBResponse(BaseModel):
    narrative_id: int
    suspicion_score: float
    organic_score: float
    graph_suspicion_score: float = 0.0
    text_coordination_score: float = 0.0
    graph_sufficient: bool = False
    graph_coverage_pct: float = 0.0
    signals: list[str]
    graph_signals: list[str] = Field(default_factory=list)
    text_signals: list[str] = Field(default_factory=list)
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
    burst_synchronized: bool = False
    burst_author_count: int = 0
    cluster_span_seconds: float = 0.0
    min_inter_arrival_seconds: float | None = None


class AstroturfImportResponse(BaseModel):
    path: str
    parsed: int
    new_rows: int
    total_in_db: int
    platform: str
    source: str
