from pathlib import Path

from heimdall.ingestion.sightings import append_ingest_sighting, load_sightings_for_narrative, summarize_sightings


def test_sightings_append_and_summarize(tmp_path: Path) -> None:
    path = tmp_path / "sightings.jsonl"
    append_ingest_sighting(
        {
            "narrative_name": "midterms_2026",
            "platform": "x",
            "event": "duplicate",
            "post_id": 1,
        },
        path=path,
    )
    append_ingest_sighting(
        {
            "narrative_name": "midterms_2026",
            "platform": "x",
            "event": "inserted",
            "post_id": 2,
        },
        path=path,
    )
    rows = load_sightings_for_narrative("midterms_2026", path=path)
    assert len(rows) == 2
    summary = summarize_sightings(rows)
    assert summary["total_resightings"] == 1
    assert summary["total_net_new"] == 1
