from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.db.models import OutrageScore, Post
from heimdall.nlp.lexicon import (
    AFFECTION,
    ANTI_AUTHORITY,
    DEHUMANIZING,
    HIGH_CONFLICT,
    NEGATIVE_LEXICON,
    RAGEBAIT_MARKERS,
    STANCE_POLARIZATION,
    STANDALONE_BITCH,
    TOXIC_PROFANITY,
)

MODEL_VERSION = "heimdall-lexicon-v2.2"
MODEL_VERSION_EMBED = f"{MODEL_VERSION}+embed-cluster"


@dataclass
class OutrageResult:
    outrage_index: float
    sentiment_label: str
    dehumanization_score: float
    anti_authority_score: float
    conflict_escalation: float
    theme_boost: float = 0.0
    emerging_theme: bool = False


class OutrageAnalyzer:
    """
    Computes an 'outrage index' from 0-1 combining sentiment proxies and
    escalation markers (dehumanization, anti-authority, ragebait patterns).
    Optional embedding clusters boost posts in lexicon-light coordinated themes.
    """

    def __init__(
        self,
        use_transformers: bool = False,
        *,
        use_embeddings: bool = False,
        embedding_model: str | None = None,
    ) -> None:
        self._sentiment_pipe = None
        self.use_embeddings = use_embeddings
        self._embedding_model = embedding_model
        if use_transformers:
            self._load_transformers()

    def _load_transformers(self) -> None:
        try:
            from transformers import pipeline

            self._sentiment_pipe = pipeline(
                "sentiment-analysis",
                model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                truncation=True,
            )
        except Exception:
            self._sentiment_pipe = None

    def analyze(
        self,
        text: str,
        *,
        theme_boost: float = 0.0,
        emerging_theme: bool = False,
    ) -> OutrageResult:
        if not text:
            return OutrageResult(0.0, "neutral", 0.0, 0.0, 0.0)

        dehuman = min(1.0, len(DEHUMANIZING.findall(text)) * 0.4)
        anti_auth = min(1.0, len(ANTI_AUTHORITY.findall(text)) * 0.35)
        rage = min(1.0, len(RAGEBAIT_MARKERS.findall(text)) * 0.3)
        conflict = min(1.0, len(HIGH_CONFLICT.findall(text)) * 0.35)
        toxic = min(1.0, len(TOXIC_PROFANITY.findall(text)) * 0.35)
        if STANDALONE_BITCH.search(text) and not AFFECTION.search(text):
            toxic = min(1.0, toxic + 0.2)
        stance = min(1.0, len(STANCE_POLARIZATION.findall(text)) * 0.28)

        sentiment_label, neg_weight = self._sentiment(text)
        caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
        punctuation_spike = min(1.0, text.count("!") * 0.12)

        has_escalation_signal = (
            neg_weight > 0.15 or dehuman > 0 or anti_auth > 0 or toxic > 0 or rage > 0
        )
        caps_boost = min(0.2, caps_ratio * 1.2) if has_escalation_signal else min(0.06, caps_ratio * 0.4)

        conflict_escalation = min(1.0, conflict + rage * 0.45 + toxic * 0.5 + caps_boost)
        outrage_index = min(
            1.0,
            0.18 * neg_weight
            + 0.2 * dehuman
            + 0.16 * anti_auth
            + 0.2 * conflict_escalation
            + 0.08 * punctuation_spike
            + 0.1 * toxic
            + 0.08 * stance
            + theme_boost,
        )

        if AFFECTION.search(text):
            outrage_index = min(outrage_index, outrage_index * 0.5 + 0.05)

        if outrage_index >= 0.55:
            sentiment_label = "high_conflict"
        elif outrage_index >= 0.32:
            sentiment_label = "escalating"
        elif emerging_theme and outrage_index >= 0.22:
            sentiment_label = "emerging_theme"

        return OutrageResult(
            outrage_index=round(outrage_index, 4),
            sentiment_label=sentiment_label,
            dehumanization_score=round(dehuman, 4),
            anti_authority_score=round(anti_auth, 4),
            conflict_escalation=round(conflict_escalation, 4),
            theme_boost=round(theme_boost, 4),
            emerging_theme=emerging_theme,
        )

    def _sentiment(self, text: str) -> tuple[str, float]:
        if self._sentiment_pipe:
            try:
                out = self._sentiment_pipe(text[:512])[0]
                label = out["label"].lower()
                score = float(out["score"])
                neg = score if "neg" in label else (1 - score) * 0.3
                return label, neg
            except Exception:
                pass
        negative_words = len(NEGATIVE_LEXICON.findall(text))
        neg_weight = min(1.0, negative_words * 0.22)
        label = "negative" if neg_weight > 0.25 else "neutral"
        return label, neg_weight

    def _theme_context(
        self,
        post_list: list[Post],
    ) -> tuple[dict[int, float], dict[int, bool]]:
        if not self.use_embeddings or len(post_list) < 3:
            return {}, {}
        from heimdall.config import get_settings
        from heimdall.nlp.embeddings import DEFAULT_EMBEDDING_MODEL
        from heimdall.nlp.theme_clusters import cluster_posts

        settings = get_settings()
        model = self._embedding_model or settings.embedding_model or DEFAULT_EMBEDDING_MODEL
        narrative_id = post_list[0].narrative_id
        report = cluster_posts(
            [(p.id, p.text) for p in post_list],
            narrative_id=narrative_id,
            model_name=model,
        )
        emerging_posts = {
            pid
            for cluster in report.clusters
            if cluster.emerging_theme
            for pid in cluster.post_ids
        }
        return report.post_theme_boost, {pid: True for pid in emerging_posts}

    async def score_and_persist(self, session: AsyncSession, post_id: int, text: str) -> bool:
        existing = await session.execute(
            select(OutrageScore).where(OutrageScore.post_id == post_id)
        )
        if existing.scalar_one_or_none():
            return False
        await self._persist(session, post_id, text)
        return True

    async def _persist(
        self,
        session: AsyncSession,
        post_id: int,
        text: str,
        *,
        theme_boost: float = 0.0,
        emerging_theme: bool = False,
        model_version: str | None = None,
    ) -> None:
        result = self.analyze(text, theme_boost=theme_boost, emerging_theme=emerging_theme)
        session.add(
            OutrageScore(
                post_id=post_id,
                outrage_index=result.outrage_index,
                sentiment_label=result.sentiment_label,
                dehumanization_score=result.dehumanization_score,
                anti_authority_score=result.anti_authority_score,
                conflict_escalation=result.conflict_escalation,
                model_version=model_version or self._model_version(),
            )
        )

    def _model_version(self) -> str:
        return MODEL_VERSION_EMBED if self.use_embeddings else MODEL_VERSION

    async def rescore_narrative(self, session: AsyncSession, narrative_id: int) -> dict:
        posts = await session.execute(select(Post).where(Post.narrative_id == narrative_id))
        post_list = posts.scalars().all()
        if not post_list:
            return {"narrative_id": narrative_id, "rescored": 0}

        boosts, emerging = self._theme_context(post_list)
        version = self._model_version()

        post_ids = [p.id for p in post_list]
        await session.execute(delete(OutrageScore).where(OutrageScore.post_id.in_(post_ids)))
        for post in post_list:
            await self._persist(
                session,
                post.id,
                post.text,
                theme_boost=boosts.get(post.id, 0.0),
                emerging_theme=emerging.get(post.id, False),
                model_version=version,
            )
        await session.commit()
        return {
            "narrative_id": narrative_id,
            "rescored": len(post_list),
            "model_version": version,
            "embedding_themes": bool(boosts),
        }
