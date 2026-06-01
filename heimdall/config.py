from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Default: SQLite file DB (no Docker). Use Postgres URL when docker compose is up.
    database_url: str = "sqlite+aiosqlite:///./heimdall.db"
    redis_url: str = "redis://localhost:6379/0"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "heimdallgraph"
    neo4j_browser_url: str = "http://localhost:7474"

    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "heimdall/0.1"

    x_bearer_token: str = ""
    x_auth_token: str = Field(
        default="",
        validation_alias=AliasChoices("X_AUTH_TOKEN", "AUTH_TOKEN"),
    )
    x_ct0: str = Field(
        default="",
        validation_alias=AliasChoices("X_CT0", "CT0"),
    )

    # X ingest guardrails (unofficial GraphQL; keep conservative)
    x_ingest_enabled: bool = True
    x_max_keywords_per_ingest: int = 5
    x_max_posts_per_ingest: int = 80
    x_max_tweets_per_search: int = 20
    x_min_seconds_between_searches: float = 3.0
    x_max_graphql_requests_per_day: int = 30
    x_rate_state_path: str = "data/x_rate_state.json"

    # Default ingester when /ingest omits platform: hackernews needs no credentials
    default_ingester: str = "hackernews"
    mastodon_instance_url: str = "https://mastodon.social"

    astroturf_tsv_path: str = "data/astroturf.tsv"
    auto_import_astroturf: bool = True

    tweet_eval_split: str = "test"  # train | validation | test

    # Rate limits (requests per window)
    ingest_requests_per_minute: int = 30
    ingest_burst: int = 5

    # Default narrative keywords for domestic polarization tracking
    default_narrative_keywords: list[str] = [
        "border crisis",
        "election fraud",
        "deep state",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
