from datetime import timedelta
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import billing
from .db import Base, engine, get_db
from .models import Episode, Series, Transaction, Unlock, User, WatchProgress, now
from .security import admin_only, current_user, make_token

app = FastAPI(title="Vertical Drama API", version="0.1.0")

# Демо-відео роздаємо самим сервером (лише для демо; для справжніх серій потрібне окреме сховище/CDN)
_static = Path(__file__).resolve().parent.parent / "static"
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=_static), name="static")


@app.on_event("startup")
def _init():
    Base.metadata.create_all(engine)


# ---------- helpers ----------
def is_vip(user: User) -> bool:
    return bool(user.vip_until and user.vip_until > now())


def can_watch(db: Session, user: User, ep: Episode) -> bool:
    if ep.number <= ep.series.free_episodes or is_vip(user):
        return True
    return db.scalar(select(Unlock.id).where(Unlock.user_id == user.id, Unlock.episode_id == ep.id)) is not None


def get_episode(db: Session, episode_id: int) -> Episode:
    ep = db.get(Episode, episode_id)
    if not ep or not ep.series.published:
        raise HTTPException(404, "episode_not_found")
    return ep


def series_out(s: Series):
    return {"id": s.id, "title": s.title, "description": s.description, "genre": s.genre,
            "poster_url": s.poster_url, "free_episodes": s.free_episodes,
            "coin_price": s.coin_price, "episodes_count": len(s.episodes)}


def wallet_out(u: User):
    return {"coins": u.coins_balance, "vip": is_vip(u),
            "vip_until": u.vip_until.isoformat() if u.vip_until else None,
            "bonus_streak": u.bonus_streak}


# ---------- auth ----------
class GuestIn(BaseModel):
    device_id: str = Field(min_length=8, max_length=128)


@app.post("/auth/guest")
def auth_guest(body: GuestIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.device_id == body.device_id))
    if not user:
        user = User(device_id=body.device_id)
        db.add(user)
        db.commit()
    return {"token": make_token(user.id), "user_id": user.id}


@app.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, **wallet_out(user)}


# ---------- catalog ----------
@app.get("/series")
def list_series(db: Session = Depends(get_db)):
    rows = db.scalars(select(Series).where(Series.published.is_(True)).order_by(Series.id)).all()
    return [series_out(s) for s in rows]


@app.get("/series/{series_id}")
def get_series(series_id: int, db: Session = Depends(get_db)):
    s = db.get(Series, series_id)
    if not s or not s.published:
        raise HTTPException(404, "series_not_found")
    return series_out(s)


@app.get("/series/{series_id}/episodes")
def list_episodes(series_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = db.get(Series, series_id)
    if not s or not s.published:
        raise HTTPException(404, "series_not_found")
    return [{"id": e.id, "number": e.number, "title": e.title, "duration_sec": e.duration_sec,
             "locked": not can_watch(db, user, e)} for e in s.episodes]


# ---------- playback / unlock ----------
@app.get("/episodes/{episode_id}/play")
def play(episode_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ep = get_episode(db, episode_id)
    if not can_watch(db, user, ep):
        raise HTTPException(402, {"error": "locked", "coin_price": ep.series.coin_price})
    nxt = next((e for e in ep.series.episodes if e.number == ep.number + 1), None)
    return {"video_url": ep.video_url, "next_episode_id": nxt.id if nxt else None}


@app.post("/episodes/{episode_id}/unlock")
def unlock(episode_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ep = get_episode(db, episode_id)
    if can_watch(db, user, ep):
        return {"unlocked": True, "charged": 0, **wallet_out(user)}
    price = ep.series.coin_price
    if user.coins_balance < price:
        raise HTTPException(402, {"error": "not_enough_coins", "need": price, "have": user.coins_balance})
    user.coins_balance -= price
    db.add(Unlock(user_id=user.id, episode_id=ep.id, method="coins"))
    db.add(Transaction(user_id=user.id, kind="unlock", coins_delta=-price))
    db.merge(user)
    db.commit()
    return {"unlocked": True, "charged": price, **wallet_out(user)}


# ---------- wallet ----------
@app.get("/wallet")
def wallet(user: User = Depends(current_user)):
    return wallet_out(user)


@app.post("/wallet/daily-bonus")
def daily_bonus(db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = now()
    if user.last_bonus_at and t - user.last_bonus_at < timedelta(hours=24):
        raise HTTPException(429, {"error": "already_claimed",
                                  "next_at": (user.last_bonus_at + timedelta(hours=24)).isoformat()})
    if user.last_bonus_at and t - user.last_bonus_at < timedelta(hours=48):
        user.bonus_streak += 1
    else:
        user.bonus_streak = 1
    amount = min(5 * user.bonus_streak, 30)
    user.coins_balance += amount
    user.last_bonus_at = t
    db.add(Transaction(user_id=user.id, kind="daily_bonus", coins_delta=amount))
    db.merge(user)
    db.commit()
    return {"bonus": amount, **wallet_out(user)}


class VerifyIn(BaseModel):
    product_id: str
    purchase_token: str = Field(min_length=4, max_length=300)


@app.post("/billing/verify")
def billing_verify(body: VerifyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if db.scalar(select(Transaction.id).where(Transaction.purchase_token == body.purchase_token)):
        return {"duplicate": True, **wallet_out(user)}  # ідемпотентність
    res = billing.verify_purchase(body.product_id, body.purchase_token)
    if not res.ok:
        raise HTTPException(400, {"error": "invalid_purchase", "reason": res.reason})
    coins = billing.COIN_PACKS.get(body.product_id, 0)
    if coins:
        user.coins_balance += coins
    else:
        start = user.vip_until if is_vip(user) else now()
        user.vip_until = start + billing.VIP_PLANS[body.product_id]
    db.add(Transaction(user_id=user.id, kind="purchase", coins_delta=coins,
                       product_id=body.product_id, purchase_token=body.purchase_token))
    db.merge(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "duplicate_token")
    return {"duplicate": False, **wallet_out(user)}


class ProgressIn(BaseModel):
    episode_id: int
    position_sec: int = Field(ge=0)


@app.post("/progress")
def progress(body: ProgressIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ep = get_episode(db, body.episode_id)
    wp = db.scalar(select(WatchProgress).where(WatchProgress.user_id == user.id, WatchProgress.episode_id == ep.id))
    if wp:
        wp.position_sec, wp.updated_at = body.position_sec, now()
    else:
        db.add(WatchProgress(user_id=user.id, episode_id=ep.id, position_sec=body.position_sec))
    db.commit()
    return {"ok": True}


# ---------- admin ----------
class SeriesIn(BaseModel):
    title: str
    description: str = ""
    genre: str = ""
    poster_url: str = ""
    free_episodes: int = 8
    coin_price: int = 20
    published: bool = True


class SeriesPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    genre: str | None = None
    poster_url: str | None = None
    free_episodes: int | None = None
    coin_price: int | None = None
    published: bool | None = None


class EpisodeIn(BaseModel):
    series_id: int
    number: int = Field(ge=1)
    title: str = ""
    video_url: str
    duration_sec: int = 0


@app.post("/admin/series", dependencies=[Depends(admin_only)])
def admin_add_series(body: SeriesIn, db: Session = Depends(get_db)):
    s = Series(**body.model_dump())
    db.add(s)
    db.commit()
    return series_out(s)


@app.patch("/admin/series/{series_id}", dependencies=[Depends(admin_only)])
def admin_patch_series(series_id: int, body: SeriesPatch, db: Session = Depends(get_db)):
    s = db.get(Series, series_id)
    if not s:
        raise HTTPException(404, "series_not_found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.commit()
    return series_out(s)


@app.post("/admin/episodes", dependencies=[Depends(admin_only)])
def admin_add_episode(body: EpisodeIn, db: Session = Depends(get_db)):
    if not db.get(Series, body.series_id):
        raise HTTPException(404, "series_not_found")
    ep = Episode(**body.model_dump())
    db.add(ep)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "episode_number_exists")
    return {"id": ep.id, "number": ep.number}


class EpisodePatch(BaseModel):
    title: str | None = None
    video_url: str | None = None
    duration_sec: int | None = Field(default=None, ge=0)


@app.patch("/admin/episodes/{episode_id}", dependencies=[Depends(admin_only)])
def admin_patch_episode(episode_id: int, body: EpisodePatch, db: Session = Depends(get_db)):
    ep = db.get(Episode, episode_id)
    if not ep:
        raise HTTPException(404, "episode_not_found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ep, k, v)
    db.commit()
    return {"id": ep.id, "number": ep.number, "video_url": ep.video_url}


@app.get("/health")
def health():
    return {"status": "ok"}
