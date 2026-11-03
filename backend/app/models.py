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


class SpinLog(Base):
    """Кожне прокручування колеса: джерело (free/grant), виграш у коїнах, день (UTC)."""
    __tablename__ = "spin_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    source: Mapped[str] = mapped_column(String(10))
    segment: Mapped[int] = mapped_column(Integer)
    coins: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SpinGrant(Base):
    """Додаткові спіни, видані за завдання (за гроші спіни не продаються)."""
    __tablename__ = "spin_grants"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(30))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class QuestClaim(Base):
    __tablename__ = "quest_claims"
    __table_args__ = (UniqueConstraint("user_id", "quest_id", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    quest_id: Mapped[str] = mapped_column(String(30))
    day: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD або "once"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class EpisodeLike(Base):
    """Лайк серії. rewarded=True, якщо за цей лайк уже видано 1 коїн (повторні лайки коїнів не дають)."""
    __tablename__ = "episode_likes"
    __table_args__ = (UniqueConstraint("user_id", "episode_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), index=True)
    liked: Mapped[bool] = mapped_column(Boolean, default=True)
    rewarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Profile(Base):
    """Публічні дані користувача: ім'я та реферальний код (колонок у users не додаємо, щоб не міняти схему)."""
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    nickname: Mapped[str] = mapped_column(String(40), default="")
    ref_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ReferralLink(Base):
    __tablename__ = "referral_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    referee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    rewarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AppRelease(Base):
    """Остання версія застосунку для сповіщення про оновлення (APK поза Google Play)."""
    __tablename__ = "app_releases"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_code: Mapped[int] = mapped_column(Integer, index=True)
    version_name: Mapped[str] = mapped_column(String(30))
    apk_url: Mapped[str] = mapped_column(String(500))
    notes: Mapped[str] = mapped_column(Text, default="")
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SeriesTranslation(Base):
    """Переклад назви й опису серіалу (мова UI глядача). Немає запису -> показуємо оригінал."""
    __tablename__ = "series_translations"
    __table_args__ = (UniqueConstraint("series_id", "lang"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), index=True)
    lang: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")


class GenreTranslation(Base):
    __tablename__ = "genre_translations"
    __table_args__ = (UniqueConstraint("genre", "lang"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    genre: Mapped[str] = mapped_column(String(60))
    lang: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(60))


class EpisodeSubtitle(Base):
    """Субтитри серії однією мовою у форматі WebVTT. Генеруються пайплайном (розпізнавання -> переклад -> вичитка)."""
    __tablename__ = "episode_subtitles"
    __table_args__ = (UniqueConstraint("episode_id", "lang"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), index=True)
    lang: Mapped[str] = mapped_column(String(8))
    vtt: Mapped[str] = mapped_column(Text, default="")
    machine: Mapped[bool] = mapped_column(Boolean, default=True)  # True = машинний переклад без вичитки
