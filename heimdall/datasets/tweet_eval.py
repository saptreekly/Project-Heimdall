"""Hugging Face cardiffnlp/tweet_eval — tweet text + benchmark labels."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from heimdall.db.models import Platform
from heimdall.ingestion.base import PlatformIngester
from heimdall.ingestion.schemas import RawPost
from heimdall.ingestion.text_clean import clean_post_text

# Subsets useful for outrage / polarization research
RAGEBAIT_SUBSETS = frozenset(
    {
        "hate",
        "offensive",
        "irony",
        "sentiment",
        "emotion",
        "stance_abortion",
        "stance_atheism",
        "stance_climate",
        "stance_feminist",
        "stance_hillary",
    }
)
ALL_SUBSETS = RAGEBAIT_SUBSETS | {"emoji"}

LABEL_NAMES: dict[str, dict[int, str]] = {
    "hate": {0: "non_hate", 1: "hate"},
    "offensive": {0: "non_offensive", 1: "offensive"},
    "irony": {0: "non_irony", 1: "irony"},
    "sentiment": {0: "negative", 1: "neutral", 2: "positive"},
    "emotion": {0: "anger", 1: "joy", 2: "optimism", 3: "sadness"},
    "stance_abortion": {0: "none", 1: "against", 2: "favor"},
    "stance_atheism": {0: "none", 1: "against", 2: "favor"},
    "stance_climate": {0: "none", 1: "against", 2: "favor"},
    "stance_feminist": {0: "none", 1: "against", 2: "favor"},
    "stance_hillary": {0: "none", 1: "against", 2: "favor"},
}


def _load_hf_dataset(subset: str, split: str):
    from datasets import load_dataset

    return load_dataset("cardiffnlp/tweet_eval", subset, split=split)


def _author_id_for_text(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"te_{digest}"


class TweetEvalIngester(PlatformIngester):
    """
    Ingest tweets from cardiffnlp/tweet_eval.
    keywords = subset names (e.g. hate, offensive, stance_hillary); defaults to hate.
    """

    def __init__(self, split: str = "test") -> None:
        self._split = split

    async def fetch_by_keywords(self, keywords: list[str], limit: int = 50) -> list[RawPost]:
        import asyncio

        subsets = _normalize_subsets(keywords)
        return await asyncio.to_thread(self._load_sync, subsets, limit)

    def _load_sync(self, subsets: list[str], limit: int) -> list[RawPost]:
        posts: list[RawPost] = []
        per_subset = max(limit // len(subsets), 1)
        base_time = datetime.now(timezone.utc)

        for subset in subsets:
            dataset = _load_hf_dataset(subset, self._split)
            label_map = LABEL_NAMES.get(subset, {})
            count = 0
            for idx, row in enumerate(dataset):
                if count >= per_subset or len(posts) >= limit:
                    break
                text = clean_post_text(row.get("text") or "")
                if not text:
                    continue
                label = int(row["label"])
                author_id = _author_id_for_text(text)
                external_id = f"{subset}-{self._split}-{idx}"
                posted_at = base_time - timedelta(minutes=len(posts))
                posts.append(
                    RawPost(
                        platform=Platform.TWEET_EVAL,
                        external_id=external_id,
                        author_id=author_id,
                        author_handle=None,
                        text=text,
                        posted_at=posted_at,
                        raw_json=json.dumps(
                            {
                                "subset": subset,
                                "split": self._split,
                                "label": label,
                                "label_name": label_map.get(label, str(label)),
                                "source": "cardiffnlp/tweet_eval",
                            }
                        ),
                    )
                )
                count += 1
        return posts[:limit]


def _normalize_subsets(keywords: list[str]) -> list[str]:
    picked = [k.strip().lower() for k in keywords if k.strip().lower() in ALL_SUBSETS]
    if picked:
        return picked
    return ["hate"]


def parse_tweet_eval_meta(raw_json: str | None) -> dict | None:
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    if data.get("source") == "cardiffnlp/tweet_eval":
        return data
    return None
