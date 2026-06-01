"""Parse platform-specific post metadata from stored raw_json."""

from __future__ import annotations

import json


def parse_x_screen_name(raw_json: str | None) -> str | None:
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None
    name = (data.get("screen_name") or "").strip()
    if not name:
        return None
    return name if name.startswith("@") else f"@{name}"


def post_status_url(platform: str, external_id: str) -> str | None:
    if platform == "x" and external_id:
        return f"https://x.com/i/web/status/{external_id}"
    return None
