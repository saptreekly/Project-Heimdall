#!/usr/bin/env python3
"""Run offline TweetEval outrage benchmark (no DB required)."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark outrage scorer on TweetEval")
    parser.add_argument(
        "--subset",
        action="append",
        help="TweetEval subset (repeatable). Default: hate, offensive, sentiment",
    )
    parser.add_argument("--split", default="test", choices=("train", "validation", "test"))
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--transformers", action="store_true")
    args = parser.parse_args()

    from heimdall.nlp.calibrate import benchmark_outrage_on_tweet_eval

    report = benchmark_outrage_on_tweet_eval(
        args.subset,
        split=args.split,
        limit_per_subset=args.limit,
        use_transformers=args.transformers,
    )
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
