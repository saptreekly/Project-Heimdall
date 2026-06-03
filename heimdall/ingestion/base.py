from abc import ABC, abstractmethod

from heimdall.ingestion.query_plan import QueryPlan
from heimdall.ingestion.schemas import RawPost


class PlatformIngester(ABC):
    @abstractmethod
    async def fetch_by_keywords(
        self,
        keywords: list[str],
        limit: int = 50,
        *,
        query_plan: QueryPlan | None = None,
    ) -> list[RawPost]:
        """Pull posts matching narrative keywords or a structured query plan."""
