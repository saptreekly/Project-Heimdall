import numpy as np

from heimdall.nlp.theme_cluster_eval import compute_cluster_metrics, evaluate_theme_report
from heimdall.nlp.theme_clusters import ThemeCluster, ThemeClusterReport


def test_compute_cluster_metrics() -> None:
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.99, 0.01],
            [0.0, 1.0],
            [0.01, 0.99],
        ],
        dtype=np.float32,
    )
    labels = np.array([0, 0, 1, 1], dtype=int)
    sil, db = compute_cluster_metrics(embeddings, labels)
    assert sil is not None
    assert db is not None


def test_evaluate_theme_report_noise_ratio() -> None:
    report = ThemeClusterReport(
        narrative_id=1,
        post_count=4,
        cluster_count=1,
        method="test",
        model="test-model",
        clusters=[
            ThemeCluster(
                cluster_id=0,
                post_ids=[1, 2],
                size=2,
                cohesion=0.8,
                lexicon_hit_rate=0.1,
                emerging_theme=False,
                label_terms=["alpha"],
                label_phrases=["alpha"],
                label_distinctiveness=0.3,
                sample_text="alpha",
            )
        ],
    )
    embeddings = np.ones((4, 8), dtype=np.float32)
    metrics = evaluate_theme_report(report, embeddings, [1, 2, 3, 4])
    assert metrics.noise_ratio == 0.5
