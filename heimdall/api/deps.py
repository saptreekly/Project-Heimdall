"""FastAPI dependencies."""

from fastapi import Header, HTTPException

from heimdall.config import get_settings


async def require_ingest_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Optional API key for mutating routes. When INGEST_API_KEY is unset, auth is disabled."""
    expected = get_settings().ingest_api_key.strip()
    if not expected:
        return
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
