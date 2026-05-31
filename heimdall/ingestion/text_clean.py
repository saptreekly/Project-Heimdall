import re
import unicodedata

_URL = re.compile(r"https?://\S+")
_MENTION = re.compile(r"@\w+")
_HASHTAG = re.compile(r"#(\w+)")
_WHITESPACE = re.compile(r"\s+")


def clean_post_text(text: str, *, strip_urls: bool = True, normalize_unicode: bool = True) -> str:
    if not text:
        return ""
    if normalize_unicode:
        text = unicodedata.normalize("NFKC", text)
    if strip_urls:
        text = _URL.sub("", text)
    text = _MENTION.sub("", text)
    text = _HASHTAG.sub(r"\1", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


def extract_hashtags(text: str) -> list[str]:
    return _HASHTAG.findall(text or "")
