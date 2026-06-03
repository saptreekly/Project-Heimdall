"""X/Twitter internal GraphQL client using session cookies (auth_token + ct0)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LFVt1IUqPHC5FhGql3xZ0H0wP6t4cE"
)
FALLBACK_QUERY_IDS = {
    "ListLatestTweetsTimeline": "RlZzktZY_9wJynoepm8ZsA",
    "SearchTimeline": "Yw6L66Pw54NHKuq4Dp7b4Q",
}
OPENAPI_PLACEHOLDER_URL = (
    "https://raw.githubusercontent.com/fa0311/twitter-openapi/"
    "refs/heads/main/src/config/placeholder.json"
)
# SearchTimeline expects the newer web feature bundle (GET often returns 401).
SEARCH_FEATURES = {
    "rweb_video_screen_enabled": False,
    "rweb_cashtags_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "rweb_cashtags_composer_attachment_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "rweb_conversational_replies_downvote_enabled": False,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}
SEARCH_FIELD_TOGGLES = {"withArticleRichContentState": False, "withArticlePlainText": False}

GRAPHQL_FEATURES = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "responsive_web_media_download_video_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "responsive_web_enhance_cards_enabled": False,
}

_query_id_cache: dict[str, str] = {}


@dataclass(frozen=True)
class ParsedXTweet:
    tweet_id: str
    author_id: str
    screen_name: str
    text: str
    created_at: datetime | None
    is_retweet: bool = False
    retweet_tweet_id: str | None = None
    retweet_author_id: str | None = None
    retweet_screen_name: str | None = None
    is_reply: bool = False
    reply_tweet_id: str | None = None
    reply_author_id: str | None = None
    is_quote: bool = False
    quote_tweet_id: str | None = None
    quote_author_id: str | None = None
    quote_screen_name: str | None = None


def _deep_get(data: Any, *keys: Any) -> Any:
    current = data
    for key in keys:
        if isinstance(key, int):
            if isinstance(current, list) and 0 <= key < len(current):
                current = current[key]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _parse_created_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _unwrap_tweet_result(result: dict[str, Any]) -> dict[str, Any] | None:
    if result.get("__typename") == "TweetTombstone":
        return None
    if result.get("__typename") == "TweetWithVisibilityResults" and result.get("tweet"):
        return result["tweet"]
    return result


def _user_ids(user: dict[str, Any]) -> tuple[str, str]:
    legacy = user.get("legacy") or {}
    core = user.get("core") or {}
    author_id = str(user.get("rest_id") or legacy.get("id_str") or "unknown")
    screen_name = str(core.get("screen_name") or legacy.get("screen_name") or "unknown")
    return author_id, screen_name


def parse_tweet_result(result: dict[str, Any]) -> ParsedXTweet | None:
    tweet_data = _unwrap_tweet_result(result)
    if not tweet_data:
        return None

    legacy = tweet_data.get("legacy")
    core = tweet_data.get("core")
    if not isinstance(legacy, dict) or not isinstance(core, dict):
        return None

    user = _deep_get(core, "user_results", "result") or {}
    if not isinstance(user, dict):
        return None
    author_id, screen_name = _user_ids(user)

    retweet_result = _deep_get(legacy, "retweeted_status_result", "result")
    is_retweet = isinstance(retweet_result, dict)
    retweet_tweet_id: str | None = None
    retweet_author_id: str | None = None
    retweet_screen_name: str | None = None

    text_source = tweet_data
    text_legacy = legacy
    if is_retweet:
        inner = _unwrap_tweet_result(retweet_result) or {}
        inner_legacy = inner.get("legacy") if isinstance(inner, dict) else {}
        inner_core = inner.get("core") if isinstance(inner, dict) else {}
        if isinstance(inner_legacy, dict) and isinstance(inner_core, dict):
            text_source = inner
            text_legacy = inner_legacy
            inner_user = _deep_get(inner_core, "user_results", "result") or {}
            if isinstance(inner_user, dict):
                retweet_author_id, retweet_screen_name = _user_ids(inner_user)
                retweet_tweet_id = str(
                    inner.get("rest_id") or inner_legacy.get("id_str") or ""
                ) or None

    note_text = _deep_get(text_source, "note_tweet", "note_tweet_results", "result", "text")
    text = (note_text or text_legacy.get("full_text") or "").strip()
    if not text:
        return None

    tweet_id = str(tweet_data.get("rest_id") or legacy.get("id_str") or "")
    if not tweet_id:
        return None

    is_reply = False
    reply_tweet_id: str | None = None
    reply_author_id: str | None = None
    reply_status = legacy.get("in_reply_to_status_id_str")
    reply_user = legacy.get("in_reply_to_user_id_str")
    if reply_status and reply_user:
        is_reply = True
        reply_tweet_id = str(reply_status)
        reply_author_id = str(reply_user)

    is_quote = False
    quote_tweet_id: str | None = None
    quote_author_id: str | None = None
    quote_screen_name: str | None = None
    if not is_retweet:
        quote_result = _deep_get(legacy, "quoted_status_result", "result")
        if isinstance(quote_result, dict):
            inner = _unwrap_tweet_result(quote_result) or {}
            inner_legacy = inner.get("legacy") if isinstance(inner, dict) else {}
            inner_core = inner.get("core") if isinstance(inner, dict) else {}
            if isinstance(inner_legacy, dict) and isinstance(inner_core, dict):
                is_quote = True
                inner_user = _deep_get(inner_core, "user_results", "result") or {}
                if isinstance(inner_user, dict):
                    quote_author_id, quote_screen_name = _user_ids(inner_user)
                    quote_tweet_id = str(
                        inner.get("rest_id") or inner_legacy.get("id_str") or ""
                    ) or None

    return ParsedXTweet(
        tweet_id=tweet_id,
        author_id=author_id,
        screen_name=screen_name,
        text=text,
        created_at=_parse_created_at(legacy.get("created_at")),
        is_retweet=is_retweet,
        retweet_tweet_id=retweet_tweet_id,
        retweet_author_id=retweet_author_id,
        retweet_screen_name=retweet_screen_name,
        is_reply=is_reply,
        reply_tweet_id=reply_tweet_id,
        reply_author_id=reply_author_id,
        is_quote=is_quote,
        quote_tweet_id=quote_tweet_id,
        quote_author_id=quote_author_id,
        quote_screen_name=quote_screen_name,
    )


def _extract_bottom_cursor(instructions: list[Any]) -> str | None:
    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        entries = instruction.get("entries") or instruction.get("moduleItems") or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            content = entry.get("content")
            if not isinstance(content, dict):
                continue
            if content.get("entryType") == "TimelineTimelineCursor":
                if content.get("cursorType") == "Bottom":
                    value = content.get("value")
                    if isinstance(value, str) and value:
                        return value
            entry_id = str(entry.get("entryId") or "")
            if "cursor-bottom" in entry_id:
                value = content.get("value")
                if isinstance(value, str) and value:
                    return value
    return None


def _iter_timeline_tweets(instructions: list[Any]) -> list[ParsedXTweet]:
    tweets: list[ParsedXTweet] = []
    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        entries = instruction.get("entries") or instruction.get("moduleItems") or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            content = entry.get("content")
            if not isinstance(content, dict):
                continue
            for result in _tweet_results_from_content(content):
                parsed = parse_tweet_result(result)
                if parsed:
                    tweets.append(parsed)
    return tweets


def _tweet_results_from_content(content: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    primary = _deep_get(content, "itemContent", "tweet_results", "result")
    if isinstance(primary, dict):
        results.append(primary)
    for nested_item in content.get("items") or []:
        nested_result = _deep_get(
            nested_item,
            "item",
            "itemContent",
            "tweet_results",
            "result",
        )
        if isinstance(nested_result, dict):
            results.append(nested_result)
    return results


def parse_list_timeline(payload: dict[str, Any]) -> list[ParsedXTweet]:
    instructions = _deep_get(
        payload,
        "data",
        "list",
        "tweets_timeline",
        "timeline",
        "instructions",
    )
    if not isinstance(instructions, list):
        return []
    return _iter_timeline_tweets(instructions)


def parse_search_timeline_page(payload: dict[str, Any]) -> tuple[list[ParsedXTweet], str | None]:
    instructions = _deep_get(
        payload,
        "data",
        "search_by_raw_query",
        "search_timeline",
        "timeline",
        "instructions",
    )
    if not isinstance(instructions, list):
        return [], None
    return _iter_timeline_tweets(instructions), _extract_bottom_cursor(instructions)


def parse_search_timeline(payload: dict[str, Any]) -> list[ParsedXTweet]:
    tweets, _cursor = parse_search_timeline_page(payload)
    return tweets


class XGraphQLClient:
    def __init__(self, auth_token: str, ct0: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._auth_token = auth_token
        self._ct0 = ct0
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self, referer: str) -> dict[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {BEARER_TOKEN}",
            "Cookie": f"auth_token={self._auth_token}; ct0={self._ct0}",
            "x-csrf-token": self._ct0,
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
            "Accept": "*/*",
            "Referer": referer,
        }

    async def _resolve_query_id(self, operation_name: str) -> str:
        cached = _query_id_cache.get(operation_name)
        if cached:
            return cached

        fallback = FALLBACK_QUERY_IDS.get(operation_name)
        try:
            response = await self._client.get(OPENAPI_PLACEHOLDER_URL)
            response.raise_for_status()
            payload = response.json()
            query_id = payload.get(operation_name, {}).get("queryId")
            if isinstance(query_id, str) and query_id:
                _query_id_cache[operation_name] = query_id
                return query_id
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError):
            pass

        if fallback:
            _query_id_cache[operation_name] = fallback
            return fallback
        raise RuntimeError(f"Unable to resolve GraphQL query id for {operation_name}")

    async def _graphql_request(
        self,
        operation_name: str,
        variables: dict[str, Any],
        *,
        referer: str,
        features: dict[str, Any] | None = None,
        field_toggles: dict[str, Any] | None = None,
        prefer_post: bool = False,
    ) -> dict[str, Any]:
        query_id = await self._resolve_query_id(operation_name)
        compact_features = {
            k: v for k, v in (features or GRAPHQL_FEATURES).items() if v is not False
        }
        url = f"https://x.com/i/api/graphql/{query_id}/{operation_name}"
        headers = self._headers(referer)

        async def _post() -> httpx.Response:
            body: dict[str, Any] = {
                "queryId": query_id,
                "variables": variables,
                "features": compact_features,
            }
            if field_toggles is not None:
                body["fieldToggles"] = field_toggles
            return await self._client.post(
                url,
                json=body,
                headers={**headers, "Content-Type": "application/json"},
            )

        async def _get() -> httpx.Response:
            params: dict[str, str] = {
                "variables": json.dumps(variables, separators=(",", ":")),
                "features": json.dumps(compact_features, separators=(",", ":")),
            }
            if field_toggles is not None:
                params["fieldToggles"] = json.dumps(field_toggles, separators=(",", ":"))
            return await self._client.get(url, params=params, headers=headers)

        if prefer_post:
            response = await _post()
        else:
            response = await _get()
            if response.status_code in (401, 404):
                response = await _post()

        if response.status_code == 401:
            raise RuntimeError(
                "X returned 401: session cookies expired or invalid. "
                "Refresh auth_token and ct0 from x.com in .env and restart the server."
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            messages = "; ".join(
                str(error.get("message", error)) for error in payload["errors"] if error
            )
            raise RuntimeError(messages or "X GraphQL request failed")
        return payload

    async def search(
        self,
        raw_query: str,
        *,
        count: int = 20,
        product: str = "Latest",
        cursor: str | None = None,
    ) -> list[ParsedXTweet]:
        tweets, _next_cursor = await self.search_page(
            raw_query,
            count=count,
            product=product,
            cursor=cursor,
        )
        return tweets

    async def search_page(
        self,
        raw_query: str,
        *,
        count: int = 20,
        product: str = "Latest",
        cursor: str | None = None,
    ) -> tuple[list[ParsedXTweet], str | None]:
        variables: dict[str, Any] = {
            "rawQuery": raw_query,
            "count": count,
            "querySource": "typed_query",
            "product": product,
        }
        if cursor:
            variables["cursor"] = cursor
        payload = await self._graphql_request(
            "SearchTimeline",
            variables,
            referer=f"https://x.com/search?q={raw_query}&src=typed_query",
            features=SEARCH_FEATURES,
            field_toggles=SEARCH_FIELD_TOGGLES,
            prefer_post=True,
        )
        return parse_search_timeline_page(payload)

    async def list_timeline(self, list_id: str, *, count: int = 20) -> list[ParsedXTweet]:
        variables = {"listId": list_id, "count": count}
        payload = await self._graphql_request(
            "ListLatestTweetsTimeline",
            variables,
            referer=f"https://x.com/i/lists/{list_id}",
        )
        return parse_list_timeline(payload)

    async def fetch_by_tweet_ids(self, tweet_ids: list[str]) -> list[ParsedXTweet]:
        """Best-effort fetch for reply-target backfill via search by tweet id."""
        found: list[ParsedXTweet] = []
        for tid in tweet_ids:
            if not tid:
                continue
            batch = await self.search(tid, count=5, product="Latest")
            for tweet in batch:
                if tweet.tweet_id == tid:
                    found.append(tweet)
                    break
        return found


async def resolve_query_id_from_bundle(operation_name: str) -> str | None:
    """Best-effort query id discovery from x.com JS bundles (used in tests/fallback)."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            html = (await client.get("https://x.com")).text
        script_urls = re.findall(
            r'(?:src|href)=["\'](https://abs\.twimg\.com/responsive-web/client-web[^"\']+\.js)["\']',
            html,
        )
        pattern = re.compile(
            r'queryId:\s*"([A-Za-z0-9_-]+)"[^}]{0,200}operationName:\s*"([^"]+)"'
        )
        for script_url in script_urls[:8]:
            async with httpx.AsyncClient(timeout=30.0) as client:
                bundle = (await client.get(script_url)).text
            for match in pattern.finditer(bundle):
                query_id, name = match.group(1), match.group(2)
                _query_id_cache.setdefault(name, query_id)
        return _query_id_cache.get(operation_name)
    except httpx.HTTPError:
        return None
