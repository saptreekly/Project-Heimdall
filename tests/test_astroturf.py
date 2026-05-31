from pathlib import Path

from heimdall.datasets.astroturf import load_astroturf_tsv

DATA = Path(__file__).resolve().parents[1] / "data" / "astroturf.tsv"


def test_load_astroturf_tsv():
    rows = load_astroturf_tsv(DATA)
    assert len(rows) >= 580
    assert rows[0][1] == "political_Bot"
    assert rows[0][0].isdigit()


def test_astroturf_ids_are_distinct_from_sample_mastodon_ids():
    """Mastodon snowflake-style IDs must not be treated as Twitter IDs."""
    rows = load_astroturf_tsv(DATA)
    twitter_ids = {uid for uid, _ in rows}
    mastodon_sample = "111264368517967707"  # from fed_politics_v3 narrative
    assert mastodon_sample not in twitter_ids
