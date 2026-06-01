from heimdall.graph.stats import build_graph_stats


def test_build_graph_stats_counts_types_and_isolated() -> None:
    authors = [
        {"author_id": "a"},
        {"author_id": "b"},
        {"author_id": "c"},
    ]
    edges = [
        {"source": "a", "target": "b", "type": "share"},
        {"source": "b", "target": "a", "type": "reply"},
    ]
    stats = build_graph_stats(authors, edges)
    assert stats["edge_count"] == 2
    assert stats["author_count"] == 3
    assert stats["connected_author_count"] == 2
    assert stats["isolated_author_count"] == 1
    assert stats["by_type"] == {"reply": 1, "share": 1}
