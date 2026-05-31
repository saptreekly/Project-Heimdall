from dataclasses import dataclass, field
from datetime import datetime

from heimdall.db.models import InteractionType, Platform


@dataclass
class RawInteraction:
    source_author_id: str
    target_author_id: str
    interaction_type: InteractionType
    occurred_at: datetime
    target_external_id: str | None = None


@dataclass
class RawPost:
    platform: Platform
    external_id: str
    author_id: str
    text: str
    posted_at: datetime
    author_handle: str | None = None
    raw_json: str | None = None
    interactions: list[RawInteraction] = field(default_factory=list)
