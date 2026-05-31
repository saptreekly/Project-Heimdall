import re
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.db.models import OutrageScore, Post

DEHUMANIZING = re.compile(
    r"\b(vermin|animals|subhuman|parasite|infest|exterminate|filth|scum|"
    r"invaded us|do not belong|no rights)\b",
    re.I,
)
ANTI_AUTHORITY = re.compile(
    r"\b(deep state|tyrann|martial law|illegitimate|stolen election|"
    r"they control|shadow government|traitors in|america\s*first|#americafirst)\b",
    re.I,
)
RAGEBAIT_MARKERS = re.compile(
    r"(!{2,}|wake up|share before|they don't want you|mainstream media won't|"
    r"you won't believe|destroying our country|hate you|nodaca|no ?daca)\b",
    re.I,
)
HIGH_CONFLICT = re.compile(
    r"\b(enemy|war on|fight back|blood|revolution|purge|eliminate|"
    r"don'?t test me|ignorant)\b",
    re.I,
)
TOXIC_PROFANITY = re.compile(
    r"\b(cunt|bitch ass|f+u+c+k+|shit)\b",
    re.I,
)
STANDALONE_BITCH = re.compile(r"\bbitch\b", re.I)
AFFECTION = re.compile(
    r"\b(i love you|ily|ilysm|thank u|thank you|my fave|with my whole heart|"
    r"spreads love|❤|💕)\b",
    re.I,
)
NEGATIVE_LEXICON = re.compile(
    r"\b(hate|destroy|evil|corrupt|lie|fake|invad|deport|illegal|"
    r"traitor|disgusting|pathetic|scum)\b",
    re.I,
)
STANCE_POLARIZATION = re.compile(
    r"\b(#semst|lock her up|crooked|witch|benghazi|climate hoax|"
    r"fake news|illegitimate|tyrant|socialist|communist|radical left|"
    r"radical right|destroy (our|the) (country|nation)|america first)\b",
    re.I,
)

MODEL_VERSION = "heimdall-lexicon-v2.1"


@dataclass
class OutrageResult:
    outrage_index: float
    sentiment_label: str
    dehumanization_score: float
    anti_authority_score: float
    conflict_escalation: float


class OutrageAnalyzer:
    """
    Computes an 'outrage index' from 0–1 combining sentiment proxies and
    escalation markers (dehumanization, anti-authority, ragebait patterns).
    v2 tuned against TweetEval hate/offensive subsets.
    """

    def __init__(self, use_transformers: bool = False) -> None:
        self._sentiment_pipe = None
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

    def analyze(self, text: str) -> OutrageResult:
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
            + 0.08 * stance,
        )

        if AFFECTION.search(text):
            outrage_index = min(outrage_index, outrage_index * 0.5 + 0.05)

        if outrage_index >= 0.55:
            sentiment_label = "high_conflict"
        elif outrage_index >= 0.32:
            sentiment_label = "escalating"

        return OutrageResult(
            outrage_index=round(outrage_index, 4),
            sentiment_label=sentiment_label,
            dehumanization_score=round(dehuman, 4),
            anti_authority_score=round(anti_auth, 4),
            conflict_escalation=round(conflict_escalation, 4),
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

    async def score_and_persist(self, session: AsyncSession, post_id: int, text: str) -> bool:
        existing = await session.execute(
            select(OutrageScore).where(OutrageScore.post_id == post_id)
        )
        if existing.scalar_one_or_none():
            return False
        await self._persist(session, post_id, text)
        return True

    async def _persist(self, session: AsyncSession, post_id: int, text: str) -> None:
        result = self.analyze(text)
        session.add(
            OutrageScore(
                post_id=post_id,
                outrage_index=result.outrage_index,
                sentiment_label=result.sentiment_label,
                dehumanization_score=result.dehumanization_score,
                anti_authority_score=result.anti_authority_score,
                conflict_escalation=result.conflict_escalation,
                model_version=MODEL_VERSION,
            )
        )

    async def rescore_narrative(self, session: AsyncSession, narrative_id: int) -> dict:
        posts = await session.execute(select(Post).where(Post.narrative_id == narrative_id))
        post_list = posts.scalars().all()
        if not post_list:
            return {"narrative_id": narrative_id, "rescored": 0}

        post_ids = [p.id for p in post_list]
        await session.execute(delete(OutrageScore).where(OutrageScore.post_id.in_(post_ids)))
        for post in post_list:
            await self._persist(session, post.id, post.text)
        await session.commit()
        return {
            "narrative_id": narrative_id,
            "rescored": len(post_list),
            "model_version": MODEL_VERSION,
        }
