from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.config import Settings, get_settings
from heimdall.db.models import OutrageScore, Post
from heimdall.nlp.lexicon import (
    AFFECTION,
    ANTI_AUTHORITY,
    CONSPIRACY,
    DEHUMANIZING,
    HIGH_CONFLICT,
    NEGATIVE_LEXICON,
    RAGEBAIT_MARKERS,
    STANCE_POLARIZATION,
    STANDALONE_BITCH,
    THREAT_VIOLENCE,
    TOXIC_PROFANITY,
)

MODEL_VERSION = "heimdall-lexicon-v2.3"
MODEL_VERSION_EMBED = f"{MODEL_VERSION}+embed-cluster"
MODEL_VERSION_TRANSFORMER = f"{MODEL_VERSION}+twitter-roberta"

ESCALATION_TIERS = frozenset({"neutral", "escalating", "high_conflict", "emerging_theme"})
POLARITIES = frozenset({"negative", "neutral", "positive"})


@dataclass
class OutrageResult:
    outrage_index: float
    sentiment_label: str
    polarity: str
    escalation_tier: str
    negativity_score: float
    ragebait_score: float
    stance_score: float
    dehumanization_score: float
    anti_authority_score: float
    conflict_escalation: float
    theme_boost: float = 0.0
    emerging_theme: bool = False


def rescore_use_embeddings(settings: Settings | None = None) -> bool:
    import os

    cfg = settings or get_settings()
    raw = os.environ.get("RESCORE_USE_EMBEDDINGS", "false").lower()
    if raw in ("1", "true", "yes"):
        return cfg.use_embedding_themes
    if raw in ("0", "false", "no"):
        return False
    return cfg.use_embedding_themes


def build_outrage_analyzer(
    settings: Settings | None = None,
    *,
    use_embeddings: bool | None = None,
) -> "OutrageAnalyzer":
    cfg = settings or get_settings()
    embed = cfg.use_embedding_themes if use_embeddings is None else use_embeddings
    return OutrageAnalyzer(
        use_transformers=cfg.use_transformer_sentiment,
        use_embeddings=embed,
        embedding_model=cfg.embedding_model,
    )


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
        self.use_transformers = use_transformers
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
            return self._empty_result()

        dehuman = min(1.0, len(DEHUMANIZING.findall(text)) * 0.4)
        anti_auth = min(1.0, len(ANTI_AUTHORITY.findall(text)) * 0.35)
        rage = min(1.0, len(RAGEBAIT_MARKERS.findall(text)) * 0.3)
        conflict = min(1.0, len(HIGH_CONFLICT.findall(text)) * 0.35)
        toxic = min(1.0, len(TOXIC_PROFANITY.findall(text)) * 0.35)
        if STANDALONE_BITCH.search(text) and not AFFECTION.search(text):
            toxic = min(1.0, toxic + 0.2)
        stance = min(1.0, len(STANCE_POLARIZATION.findall(text)) * 0.28)
        conspiracy = min(1.0, len(CONSPIRACY.findall(text)) * 0.25)
        threat = min(1.0, len(THREAT_VIOLENCE.findall(text)) * 0.4)

        polarity, negativity_score = self._polarity(text)
        caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
        punctuation_spike = min(1.0, text.count("!") * 0.12)

        has_escalation_signal = (
            negativity_score > 0.15
            or dehuman > 0
            or anti_auth > 0
            or toxic > 0
            or rage > 0
            or threat > 0
        )
        caps_boost = (
            min(0.2, caps_ratio * 1.2) if has_escalation_signal else min(0.06, caps_ratio * 0.4)
        )

        ragebait_score = min(1.0, rage + punctuation_spike * 0.35)
        conflict_escalation = min(
            1.0,
            conflict + rage * 0.45 + toxic * 0.5 + caps_boost + conspiracy * 0.2 + threat * 0.35,
        )
        outrage_index = min(
            1.0,
            0.18 * negativity_score
            + 0.2 * dehuman
            + 0.16 * anti_auth
            + 0.2 * conflict_escalation
            + 0.08 * punctuation_spike
            + 0.1 * toxic
            + 0.08 * stance
            + 0.1 * conspiracy
            + 0.12 * threat
            + theme_boost,
        )

        if AFFECTION.search(text):
            outrage_index = min(outrage_index, outrage_index * 0.5 + 0.05)
            if polarity == "negative" and outrage_index < 0.2:
                polarity = "neutral"

        escalation_tier = self._escalation_tier(outrage_index, emerging_theme)
        sentiment_label = escalation_tier

        return OutrageResult(
            outrage_index=round(outrage_index, 4),
            sentiment_label=sentiment_label,
            polarity=polarity,
            escalation_tier=escalation_tier,
            negativity_score=round(negativity_score, 4),
            ragebait_score=round(ragebait_score, 4),
            stance_score=round(stance, 4),
            dehumanization_score=round(dehuman, 4),
            anti_authority_score=round(anti_auth, 4),
            conflict_escalation=round(conflict_escalation, 4),
            theme_boost=round(theme_boost, 4),
            emerging_theme=emerging_theme,
        )

    @staticmethod
    def _empty_result() -> OutrageResult:
        return OutrageResult(
            0.0,
            "neutral",
            "neutral",
            "neutral",
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        )

    @staticmethod
    def _escalation_tier(outrage_index: float, emerging_theme: bool) -> str:
        if outrage_index >= 0.55:
            return "high_conflict"
        if outrage_index >= 0.32:
            return "escalating"
        if emerging_theme and outrage_index >= 0.22:
            return "emerging_theme"
        return "neutral"

    def _polarity(self, text: str) -> tuple[str, float]:
        if self._sentiment_pipe:
            try:
                out = self._sentiment_pipe(text[:512])[0]
                label = out["label"].lower()
                score = float(out["score"])
                if "neg" in label:
                    return "negative", score
                if "pos" in label:
                    return "positive", max(0.0, (1.0 - score) * 0.15)
                return "neutral", max(0.0, (1.0 - score) * 0.25)
            except Exception:
                pass

        negative_words = len(NEGATIVE_LEXICON.findall(text))
        neg_weight = min(1.0, negative_words * 0.22)
        if AFFECTION.search(text) and neg_weight < 0.35:
            return "positive", max(0.0, neg_weight * 0.5)
        if neg_weight > 0.2:
            return "negative", neg_weight
        return "neutral", neg_weight

    def _theme_context(
        self,
        post_list: list[Post],
    ) -> tuple[dict[int, float], dict[int, bool]]:
        if not self.use_embeddings or len(post_list) < 3:
            return {}, {}
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
                polarity=result.polarity,
                escalation_tier=result.escalation_tier,
                negativity_score=result.negativity_score,
                ragebait_score=result.ragebait_score,
                stance_score=result.stance_score,
                dehumanization_score=result.dehumanization_score,
                anti_authority_score=result.anti_authority_score,
                conflict_escalation=result.conflict_escalation,
                model_version=model_version or self._model_version(),
            )
        )

    def _model_version(self) -> str:
        if self.use_embeddings:
            return MODEL_VERSION_EMBED
        if self.use_transformers and self._sentiment_pipe:
            return MODEL_VERSION_TRANSFORMER
        return MODEL_VERSION

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
            "transformer_sentiment": bool(self._sentiment_pipe),
        }
