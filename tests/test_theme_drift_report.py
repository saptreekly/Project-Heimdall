"""Tests for theme drift comparison."""

from scripts.theme_drift_report import compare_themes


def test_compare_themes_emerged_cluster() -> None:
    baseline = {"generated_at": "2026-05-25", "clusters": []}
    current = {
        "generated_at": "2026-06-01",
        "clusters": [
            {
                "cluster_id": 1,
                "post_ids": [1, 2, 3],
                "label_terms": ["nazi", "senile"],
                "label_distinctiveness": 0.9,
            }
        ],
    }
    report = compare_themes(baseline, current, "midterms_2026")
    assert report.emerged
    assert "nazi" in report.emerged[0]


def test_compare_themes_label_drift() -> None:
    baseline = {
        "generated_at": "2026-05-25",
        "clusters": [
            {
                "cluster_id": 0,
                "post_ids": [1, 2, 3],
                "label_terms": ["wave", "red", "heat"],
                "label_distinctiveness": 0.5,
            }
        ],
    }
    current = {
        "generated_at": "2026-06-01",
        "clusters": [
            {
                "cluster_id": 9,
                "post_ids": [1, 2, 3],
                "label_terms": ["texas", "senate", "race"],
                "label_distinctiveness": 0.4,
            }
        ],
    }
    report = compare_themes(baseline, current, "midterms_2026")
    assert report.label_drift or report.vanished
