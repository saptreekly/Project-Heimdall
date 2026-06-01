"""Aggregate propagation graph stats for dashboard export."""


def build_graph_stats(authors: list[dict], edges: list[dict]) -> dict:
    """Summarize interaction edges for the Graphs panel diagnostics."""
    author_ids = {a.get("author_id") for a in authors if a.get("author_id")}
    by_type: dict[str, int] = {}
    incident: set[str] = set()

    for edge in edges:
        raw_type = (edge.get("type") or "unknown").strip().lower()
        by_type[raw_type] = by_type.get(raw_type, 0) + 1
        source = edge.get("source")
        target = edge.get("target")
        if source:
            incident.add(str(source))
        if target:
            incident.add(str(target))

    connected = incident & author_ids
    isolated = author_ids - incident

    return {
        "edge_count": len(edges),
        "author_count": len(author_ids),
        "connected_author_count": len(connected),
        "isolated_author_count": len(isolated),
        "by_type": dict(sorted(by_type.items())),
    }
