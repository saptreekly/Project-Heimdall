from heimdall.config import get_settings
from heimdall.ingestion.base import PlatformIngester


def build_tweet_eval_ingester() -> PlatformIngester:
    try:
        import datasets  # noqa: F401
    except ImportError as exc:
        raise ValueError(
            "tweet_eval requires Hugging Face datasets: pip install -e '.[hf]'"
        ) from exc
    from heimdall.datasets.tweet_eval import TweetEvalIngester

    settings = get_settings()
    return TweetEvalIngester(split=settings.tweet_eval_split)
