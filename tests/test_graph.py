import networkx as nx

from heimdall.graph.networkx_analysis import NarrativeGraphAnalyzer


def test_detects_hub_coordination():
    g = nx.DiGraph()
    g.add_node("hub", max_outrage=0.8)
    for i in range(5):
        g.add_node(f"leaf_{i}", max_outrage=0.7)
        g.add_edge("hub", f"leaf_{i}")

    assessment = NarrativeGraphAnalyzer().analyze(g, narrative_id=1)
    assert assessment.suspicion_score > 0
    assert "single_hub_dominates_shares" in assessment.signals
