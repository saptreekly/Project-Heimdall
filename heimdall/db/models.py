import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Platform(str, enum.Enum):
    REDDIT = "reddit"
    X = "x"
    MOCK = "mock"
    HACKERNEWS = "hackernews"
    MASTODON = "mastodon"
    TWEET_EVAL = "tweet_eval"


class Narrative(Base):
    __tablename__ = "narratives"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    keywords: Mapped[str] = mapped_column(Text)  # comma-separated query terms
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    posts: Mapped[list["Post"]] = relationship(back_populates="narrative")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index(
            "ix_posts_narrative_platform_external",
            "narrative_id",
            "platform",
            "external_id",
            unique=True,
        ),
        Index("ix_posts_narrative_created", "narrative_id", "posted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    narrative_id: Mapped[int] = mapped_column(ForeignKey("narratives.id"))
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, values_callable=lambda p: [m.value for m in p], native_enum=False)
    )
    external_id: Mapped[str] = mapped_column(String(128))
    author_id: Mapped[str] = mapped_column(String(128))
    author_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    narrative: Mapped["Narrative"] = relationship(back_populates="posts")
    scores: Mapped[list["OutrageScore"]] = relationship(back_populates="post")
    edges_out: Mapped[list["InteractionEdge"]] = relationship(
        back_populates="source_post",
        foreign_keys="InteractionEdge.source_post_id",
    )


class OutrageScore(Base):
    __tablename__ = "outrage_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), unique=True)
    outrage_index: Mapped[float] = mapped_column(Float)
    sentiment_label: Mapped[str] = mapped_column(String(32))
    dehumanization_score: Mapped[float] = mapped_column(Float, default=0.0)
    anti_authority_score: Mapped[float] = mapped_column(Float, default=0.0)
    conflict_escalation: Mapped[float] = mapped_column(Float, default=0.0)
    model_version: Mapped[str] = mapped_column(String(64))
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    post: Mapped["Post"] = relationship(back_populates="scores")


class InteractionType(str, enum.Enum):
    RETWEET = "retweet"
    REPLY = "reply"
    QUOTE = "quote"
    SHARE = "share"
    CROSSPOST = "crosspost"


class KnownBotAccount(Base):
    """Ground-truth bot labels from external datasets (e.g. IU astroturf)."""

    __tablename__ = "known_bot_accounts"
    __table_args__ = (
        Index("ix_known_bot_platform_author", "platform", "author_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), default="x")
    author_id: Mapped[str] = mapped_column(String(128))
    label: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InteractionEdge(Base):
    """Directed edge: source amplified or replied to target (propagation graph)."""

    __tablename__ = "interaction_edges"
    __table_args__ = (Index("ix_edges_narrative", "narrative_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    narrative_id: Mapped[int] = mapped_column(ForeignKey("narratives.id"))
    source_post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    target_post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), nullable=True)
    source_author_id: Mapped[str] = mapped_column(String(128))
    target_author_id: Mapped[str] = mapped_column(String(128))
    interaction_type: Mapped[InteractionType] = mapped_column(
        Enum(InteractionType, values_callable=lambda t: [m.value for m in t], native_enum=False)
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    source_post: Mapped["Post"] = relationship(
        back_populates="edges_out",
        foreign_keys=[source_post_id],
    )
