#!/usr/bin/env python3
"""Fail CI when dashboard snapshot export is missing or empty."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "web" / "public" / "data" / "snapshot.json"
PREVIOUS = ROOT / "data" / "dashboard" / ".snapshot_smoke_previous.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from heimdall.nlp.outrage import MODEL_VERSION  # noqa: E402


def validate_sentiment_bundle(bundle: dict, *, strict: bool = False) -> list[str]:
    """Return list of validation errors (empty if OK)."""
    errors: list[str] = []
    sentiment = bundle.get("sentiment")
    if not isinstance(sentiment, dict):
        return ["missing sentiment object"] if strict else errors

    for key in ("buckets", "trend"):
        if key not in sentiment:
            errors.append(f"sentiment missing {key}")

    if strict:
        for key in ("divergence_days", "week_over_week"):
            if key not in sentiment:
                errors.append(f"sentiment missing {key}")
        posts = bundle.get("posts") or []
        if posts:
            sample = posts[0]
            for key in ("polarity", "escalation_tier", "negativity_score"):
                if key not in sample:
                    errors.append(f"post missing {key}")
        provenance = bundle.get("provenance") or {}
        version = str(provenance.get("outrage_model_version") or "")
        if version and not version.startswith(MODEL_VERSION):
            errors.append(f"outrage_model_version not {MODEL_VERSION}: {version}")
    return errors


def main() -> int:
    import os

    parser = __import__("argparse").ArgumentParser(description=__doc__)
    parser.add_argument(
        "-s",
        "--snapshot",
        type=Path,
        default=SNAPSHOT,
        help="Path to snapshot.json (default: web/public/data/snapshot.json)",
    )
    args = parser.parse_args()
    snapshot_path = args.snapshot

    if not snapshot_path.is_file():
        print(f"Missing {snapshot_path}", file=sys.stderr)
        return 1

    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    generated = data.get("generated_at")
    if not generated:
        print("snapshot.json missing generated_at", file=sys.stderr)
        return 1

    narratives = data.get("narratives") or []
    if not narratives:
        print("snapshot.json has no narratives", file=sys.stderr)
        return 1

    total_posts = 0
    for summary in narratives:
        nid = str(summary["id"])
        bundle = data.get("by_narrative_id", {}).get(nid, {})
        total_posts += len(bundle.get("posts") or [])

    if total_posts < 1:
        print("snapshot.json has zero posts across narratives", file=sys.stderr)
        return 1

    strict = os.environ.get("SNAPSHOT_SENTIMENT_STRICT", "").lower() in (
        "1",
        "true",
        "yes",
    )
    for summary in narratives:
        nid = str(summary["id"])
        bundle = data.get("by_narrative_id", {}).get(nid, {})
        errors = validate_sentiment_bundle(bundle, strict=strict)
        for err in errors:
            msg = f"narrative {summary.get('name', nid)}: {err}"
            if strict:
                print(msg, file=sys.stderr)
            else:
                print(f"Warning: {msg}", file=sys.stderr)

    if strict:
        for summary in narratives:
            nid = str(summary["id"])
            bundle = data.get("by_narrative_id", {}).get(nid, {})
            if validate_sentiment_bundle(bundle, strict=True):
                return 1

    print(f"OK: {len(narratives)} narrative(s), {total_posts} posts, generated_at={generated}")

    if PREVIOUS.is_file():
        try:
            prev = json.loads(PREVIOUS.read_text(encoding="utf-8"))
            prev_at = prev.get("generated_at")
            if prev_at and generated <= prev_at:
                print(
                    f"Warning: generated_at did not advance ({prev_at} -> {generated})",
                    file=sys.stderr,
                )
        except json.JSONDecodeError:
            pass

    PREVIOUS.parent.mkdir(parents=True, exist_ok=True)
    PREVIOUS.write_text(
        json.dumps({"generated_at": generated, "checked_at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
