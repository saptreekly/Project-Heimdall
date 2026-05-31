"""Neo4j export for interactive graph visualization in Browser / Bloom."""

from neo4j import AsyncGraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from heimdall.config import get_settings
from heimdall.graph.export import GraphExportPayload


class Neo4jGraphSync:
    def __init__(self) -> None:
        settings = get_settings()
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self._browser_url = settings.neo4j_browser_url

    async def close(self) -> None:
        await self._driver.close()

    async def ping(self) -> bool:
        try:
            async with self._driver.session() as session:
                await session.run("RETURN 1")
            return True
        except (ServiceUnavailable, Neo4jError, OSError):
            return False

    async def sync_narrative(self, payload: GraphExportPayload) -> dict:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (n:Narrative {id: $narrative_id})
                OPTIONAL MATCH (n)<-[:IN_NARRATIVE]-(p:Post)
                OPTIONAL MATCH (n)<-[:PARTICIPATES_IN]-(a:Author)
                DETACH DELETE p, a
                """,
                narrative_id=payload.narrative_id,
            )
            await session.run(
                """
                MERGE (n:Narrative {id: $narrative_id})
                SET n.name = $name,
                    n.keywords = $keywords,
                    n.updated_at = datetime(),
                    n.suspicion_score = $suspicion,
                    n.organic_score = $organic,
                    n.cib_signals = $signals
                """,
                narrative_id=payload.narrative_id,
                name=payload.narrative_name,
                keywords=payload.keywords,
                suspicion=payload.cib.get("suspicion_score") if payload.cib else None,
                organic=payload.cib.get("organic_score") if payload.cib else None,
                signals=payload.cib.get("signals", []) if payload.cib else [],
            )

            if payload.authors:
                await session.run(
                    """
                    UNWIND $authors AS author
                    MATCH (n:Narrative {id: $narrative_id})
                    MERGE (a:Author {id: author.author_id})
                    SET a.handle = author.handle,
                        a.max_outrage = author.max_outrage,
                        a.post_count = author.post_count,
                        a.known_bot = coalesce(author.known_bot, false),
                        a.bot_label = author.bot_label
                    MERGE (a)-[:PARTICIPATES_IN]->(n)
                    """,
                    narrative_id=payload.narrative_id,
                    authors=payload.authors,
                )

            if payload.posts:
                await session.run(
                    """
                    UNWIND $posts AS post
                    MATCH (n:Narrative {id: $narrative_id})
                    MERGE (a:Author {id: post.author_id})
                    SET a.handle = coalesce(post.handle, a.handle)
                    MERGE (p:Post {id: post.post_id})
                    SET p.external_id = post.external_id,
                        p.platform = post.platform,
                        p.text = post.text,
                        p.posted_at = post.posted_at,
                        p.outrage_index = post.outrage_index,
                        p.sentiment_label = post.sentiment_label
                    MERGE (a)-[:POSTED]->(p)
                    MERGE (p)-[:IN_NARRATIVE]->(n)
                    """,
                    narrative_id=payload.narrative_id,
                    posts=payload.posts,
                )

            if payload.amplifications:
                await session.run(
                    """
                    UNWIND $edges AS edge
                    MATCH (n:Narrative {id: $narrative_id})
                    MERGE (s:Author {id: edge.source})
                    MERGE (t:Author {id: edge.target})
                    MERGE (s)-[r:AMPLIFIED {type: edge.type}]->(t)
                    SET r.weight = coalesce(r.weight, 0) + 1,
                        r.source_post_id = edge.source_post_id,
                        r.target_post_id = edge.target_post_id
                    MERGE (s)-[:PARTICIPATES_IN]->(n)
                    MERGE (t)-[:PARTICIPATES_IN]->(n)
                    """,
                    narrative_id=payload.narrative_id,
                    edges=payload.amplifications,
                )

        return {
            "narrative_id": payload.narrative_id,
            "authors_written": len(payload.authors),
            "posts_written": len(payload.posts),
            "edges_written": len(payload.amplifications),
            "neo4j_browser": self._browser_url,
            "sample_query": (
                f"MATCH (n:Narrative {{id: {payload.narrative_id}}})"
                "<-[:PARTICIPATES_IN]-(a:Author)-[r:AMPLIFIED]->(b:Author) "
                "RETURN n, a, r, b LIMIT 100"
            ),
        }
