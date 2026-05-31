from abc import ABC, abstractmethod

from heimdall.ingestion.schemas import RawPost


class PlatformIngester(ABC):
    @abstractmethod
    async def fetch_by_keywords(self, keywords: list[str], limit: int = 50) -> list[RawPost]:
        """Pull posts matching narrative keywords."""
