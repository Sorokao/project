from datetime import datetime, timezone
from sqlalchemy import ForeignKey, String, Integer, DateTime, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    vip_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    coins_balance: Mapped[int] = mapped_column(Integer, default=0)
    last_bonus_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bonus_streak: Mapped[int] = mapped_column(Integer, default=0)


class Series(Base):
    __tablename__ = "series"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    genre: Mapped[str] = mapped_column(String(60), default="")
    poster_url: Mapped[str] = mapped_column(String(500), default="")
    free_episodes: Mapped[int] = mapped_column(Integer, default=8)
    coin_price: Mapped[int] = mapped_column(Integer, default=20)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    episodes: Mapped[list["Episode"]] = relationship(back_populates="series", order_by="Episode.number")


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (UniqueConstraint("series_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), default="")
    video_url: Mapped[str] = mapped_column(String(500))
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    series: Mapped[Series] = relationship(back_populates="episodes")


class Unlock(Base):
    __tablename__ = "unlocks"
    __table_args__ = (UniqueConstraint("user_id", "episode_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"))
    method: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    coins_delta: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[str] = mapped_column(String(80), default="")
    purchase_token: Mapped[str | None] = mapped_column(String(300), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class WatchProgress(Base):
    __tablename__ = "watch_progress"
    __table_args__ = (UniqueConstraint("user_id", "episode_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"))
    position_sec: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "series_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
