"""Detect fin-twit / crypto ticker spam that drowns narrative theme clustering."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9']{2,}")

# Tickers and fin-social vocabulary that rarely indicate a political narrative frame.
MARKET_TICKERS = frozenset(
    {
        "ath",
        "binance",
        "bitcoin",
        "bnb",
        "btc",
        "call",
        "calls",
        "coin",
        "coinbase",
        "crypto",
        "defi",
        "djt",
        "dji",
        "doge",
        "dow",
        "eth",
        "ethereum",
        "etf",
        "etfs",
        "fomc",
        "futures",
        "gld",
        "goog",
        "iv",
        "iwm",
        "macd",
        "meme",
        "memes",
        "meta",
        "mkt",
        "msft",
        "nasdaq",
        "ndx",
        "nft",
        "nfts",
        "nvda",
        "oi",
        "option",
        "options",
        "pp",
        "ppi",
        "put",
        "puts",
        "qqq",
        "rsi",
        "slv",
        "sol",
        "spx",
        "spy",
        "token",
        "tokens",
        "tsla",
        "vix",
        "xrp",
        "yield",
    }
)

_MARKET_REGEXES = (
    re.compile(r"\$\s?[a-z]{1,5}\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s*%", re.I),
    re.compile(r"/(?:10y|2y|30y)[a-z]*", re.I),
    re.compile(r"\\10y", re.I),
    re.compile(r"\b(?:open|close|pre|post)market\b", re.I),
    re.compile(r"\b(?:spx|ndx|dji|qqq|iwm|vix)\b", re.I),
)

MARKET_CHATTER_POST_THRESHOLD = 0.42
MARKET_CHATTER_CLUSTER_THRESHOLD = 0.32
MARKET_CLUSTER_ID = -2


def market_stopwords() -> frozenset[str]:
    return MARKET_TICKERS


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def market_chatter_score(text: str) -> float:
    """Return 0–1 score for fin-twit / crypto ticker style posts."""
    raw = text or ""
    lowered = raw.lower()
    tokens = _tokens(raw)
    if not tokens:
        return 0.0

    alpha_tokens = [t for t in tokens if t.isalpha()]
    ticker_hits = sum(1 for t in alpha_tokens if t in MARKET_TICKERS)
    ticker_rate = ticker_hits / max(len(alpha_tokens), 1)

    regex_hits = sum(1 for pattern in _MARKET_REGEXES if pattern.search(raw))
    emoji_hits = len(re.findall(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]", raw))
    emoji_rate = min(1.0, emoji_hits / 8.0)

    # Dense symbol runs like "BTC/GLD/SPX" or "MKT/NDX+1.4%"
    slash_runs = len(re.findall(r"[a-z]{2,5}/[a-z]{2,5}", lowered))
    slash_rate = min(1.0, slash_runs / 3.0)

    score = (
        0.5 * ticker_rate
        + 0.2 * min(1.0, regex_hits / 2.0)
        + 0.15 * emoji_rate
        + 0.15 * slash_rate
    )
    return round(min(1.0, score), 4)


def is_market_chatter_post(text: str) -> bool:
    return market_chatter_score(text) >= MARKET_CHATTER_POST_THRESHOLD


def cluster_market_chatter_rate(texts: list[str]) -> float:
    if not texts:
        return 0.0
    scores = [market_chatter_score(t) for t in texts]
    return round(sum(scores) / len(scores), 4)


def labels_are_market_heavy(labels: list[str]) -> bool:
    if not labels:
        return False
    market_parts = 0
    total_parts = 0
    for label in labels:
        for part in label.lower().split():
            total_parts += 1
            if part in MARKET_TICKERS or part == "mkt":
                market_parts += 1
    if total_parts == 0:
        return False
    if market_parts / total_parts >= 0.5:
        return True
    first = labels[0].lower().split()
    return bool(first and first[0] in MARKET_TICKERS)


def is_market_chatter_cluster(texts: list[str], labels: list[str]) -> bool:
    rate = cluster_market_chatter_rate(texts)
    if rate >= MARKET_CHATTER_CLUSTER_THRESHOLD:
        return True
    return labels_are_market_heavy(labels)
