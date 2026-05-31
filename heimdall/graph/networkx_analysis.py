from dataclasses import dataclass, field

import networkx as nx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.db.models import InteractionEdge, OutrageScore, Post


@dataclass
class PropagationMetrics:
    node_count: int
    edge_count: int
    density: float
    top_amplifiers: list[dict] = field(default_factory=list)
    coordinated_clusters: list[dict] = field(default_factory=list)
    organic_score: float = 0.0


@dataclass
class CIBAssessment:
    """Coordinated Inauthentic Behavior heuristic assessment."""

    narrative_id: int
    suspicion_score: float  # 0 = likely organic, 1 = likely coordinated
    signals: list[str]
    metrics: PropagationMetrics


class NarrativeGraphAnalyzer:
    """
    Builds author-level propagation graphs from interaction edges and applies
    heuristics for botnet / coordinated amplification detection.
    """

    async def build_graph(self, session: AsyncSession, narrative_id: int) -> nx.DiGraph:
        edges_result = await session.execute(
            select(InteractionEdge).where(InteractionEdge.narrative_id == narrative_id)
        )
        edges = edges_result.scalars().all()

        posts_result = await session.execute(
            select(Post).where(Post.narrative_id == narrative_id)
        )
        posts = {p.id: p for p in posts_result.scalars().all()}

        scores_result = await session.execute(
            select(OutrageScore).join(Post).where(Post.narrative_id == narrative_id)
        )
        outrage_by_post = {s.post_id: s.outrage_index for s in scores_result.scalars().all()}

        g = nx.DiGraph()
        for post in posts.values():
            outrage = outrage_by_post.get(post.id, 0.0)
            g.add_node(
                post.author_id,
                handle=post.author_handle,
                post_count=g.nodes[post.author_id].get("post_count", 0) + 1
                if post.author_id in g
                else 1,
                max_outrage=max(
                    outrage,
                    g.nodes[post.author_id].get("max_outrage", 0.0) if post.author_id in g else 0.0,
                ),
            )

        for edge in edges:
            w = 1.0
            if edge.source_author_id in g and edge.target_author_id in g:
                g.add_edge(edge.source_author_id, edge.target_author_id, weight=w)
            else:
                g.add_edge(edge.source_author_id, edge.target_author_id, weight=w)

        return g

    def analyze(self, g: nx.DiGraph, narrative_id: int) -> CIBAssessment:
        signals: list[str] = []
        n = g.number_of_nodes()
        m = g.number_of_edges()
        density = nx.density(g) if n > 1 else 0.0

        in_degrees = dict(g.in_degree())
        out_degrees = dict(g.out_degree())
        amplifiers = sorted(
            [
                {
                    "author_id": node,
                    "out_degree": out_degrees.get(node, 0),
                    "in_degree": in_degrees.get(node, 0),
                    "max_outrage": g.nodes[node].get("max_outrage", 0.0),
                }
                for node in g.nodes
            ],
            key=lambda x: x["out_degree"],
            reverse=True,
        )[:10]

        clusters: list[dict] = []
        if n >= 3:
            undirected = g.to_undirected()
            components = list(nx.connected_components(undirected))
            for i, comp in enumerate(components):
                if len(comp) < 3:
                    continue
                subgraph = g.subgraph(comp)
                comp_edges = subgraph.number_of_edges()
                comp_nodes = len(comp)
                internal_density = comp_edges / max(comp_nodes * (comp_nodes - 1), 1)
                if internal_density > 0.4:
                    signals.append(f"dense_cluster_{i}_size_{comp_nodes}")
                    clusters.append(
                        {
                            "cluster_id": i,
                            "size": comp_nodes,
                            "internal_density": round(internal_density, 4),
                            "members": list(comp)[:20],
                        }
                    )

        # Low diversity + high out-degree hub suggests coordination
        suspicion = 0.0
        if n > 0 and m > 0:
            hub_ratio = max(out_degrees.values()) / m if m else 0
            if hub_ratio > 0.5:
                signals.append("single_hub_dominates_shares")
                suspicion += 0.35
            if density > 0.15 and n >= 5:
                signals.append("abnormally_high_graph_density")
                suspicion += 0.25
            if clusters:
                suspicion += min(0.4, 0.15 * len(clusters))

        avg_outrage = (
            sum(g.nodes[n].get("max_outrage", 0) for n in g.nodes) / n if n else 0.0
        )
        if avg_outrage > 0.55 and suspicion > 0.2:
            signals.append("high_outrage_coordinated_push")

        suspicion = min(1.0, suspicion)
        organic_score = round(1.0 - suspicion, 4)

        metrics = PropagationMetrics(
            node_count=n,
            edge_count=m,
            density=round(density, 4),
            top_amplifiers=amplifiers,
            coordinated_clusters=clusters,
            organic_score=organic_score,
        )

        return CIBAssessment(
            narrative_id=narrative_id,
            suspicion_score=round(suspicion, 4),
            signals=signals,
            metrics=metrics,
        )

    async def assess_narrative(self, session: AsyncSession, narrative_id: int) -> CIBAssessment:
        g = await self.build_graph(session, narrative_id)
        return self.analyze(g, narrative_id)
