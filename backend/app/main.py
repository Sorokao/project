import secrets
from contextvars import ContextVar
from datetime import timedelta
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from . import billing
from .db import Base, engine, get_db
from .models import (AppRelease, Episode, EpisodeLike, EpisodeSubtitle, Favorite, GenreTranslation, Profile, QuestClaim, ReferralLink, Series, SeriesTranslation, SpinGrant,
                     SpinLog, Transaction, Unlock, User, WatchProgress, now)
from .security import admin_only, current_user, make_token

app = FastAPI(title="Vertical Drama API", version="0.1.0")

# Демо-відео роздаємо самим сервером (лише для демо; для справжніх серій потрібне окреме сховище/CDN)
_static = Path(__file__).resolve().parent.parent / "static"
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=_static), name="static")


LANGS = {"uk", "en", "de", "fr", "pl", "es", "pt", "it", "sr", "hr", "cnr", "el", "tr", "nl", "ro", "cs", "sk", "hu", "sl", "bg", "sq", "mk", "bs", "sv", "da", "no", "lt", "lv", "et"}
_lang: ContextVar[str] = ContextVar("lang", default="en")


@app.middleware("http")
async def _lang_mw(request: Request, call_next):
    code = (request.headers.get("x-lang") or "en").lower().split("-")[0]
    tok = _lang.set(code if code in LANGS else "en")
    try:
        return await call_next(request)
    finally:
        _lang.reset(tok)


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


def tr_genre(db: Session | None, genre: str) -> str:
    lang = _lang.get()
    if not genre or lang == "uk" or db is None:
        return genre
    g = db.scalar(select(GenreTranslation.name).where(GenreTranslation.genre == genre, GenreTranslation.lang == lang))
    return g or genre


def series_out(s: Series):
    title, desc, genre = s.title, s.description, s.genre
    lang = _lang.get()
    if lang != "uk":
        db = object_session(s)
        if db is not None:
            tr = db.scalar(select(SeriesTranslation).where(SeriesTranslation.series_id == s.id, SeriesTranslation.lang == lang))
            if tr:
                title, desc = tr.title or title, tr.description or desc
            genre = tr_genre(db, genre)
    return {"id": s.id, "title": title, "description": desc, "genre": genre,
            "poster_url": s.poster_url, "free_episodes": s.free_episodes,
            "coin_price": s.coin_price, "episodes_count": len(s.episodes)}


def bonus_state(u: User):
    """Чи доступний щоденний бонус, яким він буде і яка серія днів."""
    t = now()
    if not u.last_bonus_at or t - u.last_bonus_at >= timedelta(hours=48):
        return True, 1, None
    if t - u.last_bonus_at >= timedelta(hours=24):
        return True, u.bonus_streak + 1, None
    return False, u.bonus_streak + 1, (u.last_bonus_at + timedelta(hours=24)).isoformat()


def today() -> str:
    return now().strftime("%Y-%m-%d")


def first_purchase_available(db: Session, u: User) -> bool:
    return db.scalar(select(Transaction.id).where(Transaction.user_id == u.id, Transaction.kind == "purchase",
                                                  Transaction.coins_delta > 0)) is None


def free_spin_available(db: Session, u: User) -> bool:
    return db.scalar(select(SpinLog.id).where(SpinLog.user_id == u.id, SpinLog.day == today(),
                                              SpinLog.source == "free")) is None


def grants_left(db: Session, u: User) -> int:
    return db.scalar(select(func.count(SpinGrant.id)).where(SpinGrant.user_id == u.id, SpinGrant.used.is_(False))) or 0


LIKE_REWARD, LIKE_DAILY_CAP = 1, 20   # 1 коїн за новий лайк, до 20 коїнів на добу (= 1 серія)


def likes_today(db: Session, u: User) -> int:
    day_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count(Transaction.id)).where(
        Transaction.user_id == u.id, Transaction.kind == "like", Transaction.created_at >= day_start)) or 0


def wallet_out(u: User):
    available, next_streak, next_at = bonus_state(u)
    db = object_session(u)
    extra = {}
    if db is not None:
        free = free_spin_available(db, u)
        extra = {"likes_today": likes_today(db, u), "likes_cap": LIKE_DAILY_CAP,
                 "first_purchase_available": first_purchase_available(db, u), "wheel_free": free,
                 "spins": (1 if free else 0) + grants_left(db, u)}
    return {**extra, "coins": u.coins_balance, "vip": is_vip(u),
            "vip_until": u.vip_until.isoformat() if u.vip_until else None,
            "bonus_streak": u.bonus_streak if not available or next_streak > 1 else 0,
            "bonus_available": available, "next_bonus": min(5 * next_streak, 30),
            "next_bonus_at": next_at}


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
def list_series(q: str | None = None, genre: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Series).where(Series.published.is_(True))
    if genre:
        stmt = stmt.where(Series.genre == genre)
    rows = db.scalars(stmt.order_by(Series.id)).all()
    if q:  # фільтр у Python: lower() в SQLite/Postgres(C-локаль) не знижує регістр кирилиці
        needle = q.strip().casefold()
        rows = [x for x in rows if needle in x.title.casefold()]
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
    ids = [e.id for e in s.episodes]
    mine = set(db.scalars(select(EpisodeLike.episode_id).where(
        EpisodeLike.user_id == user.id, EpisodeLike.liked.is_(True), EpisodeLike.episode_id.in_(ids))).all())
    counts = dict(db.execute(select(EpisodeLike.episode_id, func.count(EpisodeLike.id)).where(
        EpisodeLike.liked.is_(True), EpisodeLike.episode_id.in_(ids)).group_by(EpisodeLike.episode_id)).all())
    return [{"id": e.id, "number": e.number, "title": e.title, "duration_sec": e.duration_sec,
             "locked": not can_watch(db, user, e), "liked": e.id in mine, "likes": counts.get(e.id, 0)}
            for e in s.episodes]


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
    bonus = 0
    if coins:
        if first_purchase_available(db, user):
            bonus = billing.FIRST_PURCHASE_BONUS.get(body.product_id, billing.FIRST_PURCHASE_DEFAULT)
        coins += bonus
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
    return {"duplicate": False, "first_bonus": bonus, **wallet_out(user)}


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
    settle_referral(db, user)
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



# ---------- home / favorites / continue ----------
def continue_items(db: Session, user: User, limit: int = 10):
    rows = db.execute(
        select(WatchProgress, Episode, Series)
        .join(Episode, Episode.id == WatchProgress.episode_id)
        .join(Series, Series.id == Episode.series_id)
        .where(WatchProgress.user_id == user.id, Series.published.is_(True))
        .order_by(WatchProgress.updated_at.desc())
    ).all()
    seen, out = set(), []
    for wp, ep, s in rows:
        if s.id in seen:
            continue
        seen.add(s.id)
        out.append({"series": series_out(s), "episode_id": ep.id, "episode_number": ep.number,
                    "position_sec": wp.position_sec, "duration_sec": ep.duration_sec})
        if len(out) >= limit:
            break
    return out


@app.get("/me/continue")
def me_continue(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return continue_items(db, user)


@app.get("/me/favorites")
def me_favorites(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Series).join(Favorite, Favorite.series_id == Series.id)
                      .where(Favorite.user_id == user.id, Series.published.is_(True))
                      .order_by(Favorite.created_at.desc())).all()
    return [series_out(s) for s in rows]


@app.put("/me/favorites/{series_id}")
def add_favorite(series_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not db.get(Series, series_id):
        raise HTTPException(404, "series_not_found")
    if not db.scalar(select(Favorite.id).where(Favorite.user_id == user.id, Favorite.series_id == series_id)):
        db.add(Favorite(user_id=user.id, series_id=series_id))
        db.commit()
    return {"favorite": True}


@app.delete("/me/favorites/{series_id}")
def remove_favorite(series_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    fav = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.series_id == series_id))
    if fav:
        db.delete(fav)
        db.commit()
    return {"favorite": False}


@app.get("/home")
def home(db: Session = Depends(get_db), user: User = Depends(current_user)):
    allp = db.scalars(select(Series).where(Series.published.is_(True)).order_by(Series.id.desc())).all()
    views = dict(db.execute(
        select(Episode.series_id, func.count(func.distinct(WatchProgress.user_id)))
        .join(WatchProgress, WatchProgress.episode_id == Episode.id).group_by(Episode.series_id)).all())
    popular = sorted(allp, key=lambda x: (-views.get(x.id, 0), -x.id))
    rows = [{"key": "new", "title": "New", "items": [series_out(x) for x in allp[:10]]},
            {"key": "popular", "title": "Popular", "items": [series_out(x) for x in popular[:10]]}]
    genres = []
    for x in allp:
        if x.genre and x.genre not in genres:
            genres.append(x.genre)
    for g in genres:
        rows.append({"key": "genre", "title": tr_genre(db, g), "items": [series_out(x) for x in allp if x.genre == g][:10]})
    return {"featured": [series_out(x) for x in popular[:4]], "continue_watching": continue_items(db, user),
            "genres": [tr_genre(db, g) for g in genres], "rows": rows}


def bundle_discount(n: int) -> float:
    """Чим більше серій одним пакетом, тим більша знижка."""
    return 0.0 if n < 2 else 0.10 if n < 5 else 0.15 if n < 10 else 0.25 if n < 20 else 0.35


def bundle_price(n: int, coin_price: int) -> int:
    return round(n * coin_price * (1 - bundle_discount(n)))


class BundleIn(BaseModel):
    from_episode_id: int
    count: int = Field(ge=1, le=100)


@app.get("/series/{series_id}/bundles")
def bundle_options(series_id: int, from_episode_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Варіанти пакетів: 1 серія, 5 серій і «усі решта» (якщо їх більше 5)."""
    s = db.get(Series, series_id)
    start = db.get(Episode, from_episode_id)
    if not s or not s.published or not start or start.series_id != series_id:
        raise HTTPException(404, "not_found")
    locked = [e for e in s.episodes if e.number >= start.number and not can_watch(db, user, e)]
    counts = [n for n in (1, 5) if n <= len(locked)]
    if len(locked) > 5:
        counts.append(len(locked))
    return [{"count": n, "price": bundle_price(n, s.coin_price), "full_price": n * s.coin_price,
             "discount_pct": round(bundle_discount(n) * 100), "all": n == len(locked) and n > 5} for n in counts]


@app.post("/series/{series_id}/unlock-bundle")
def unlock_bundle(series_id: int, body: BundleIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = db.get(Series, series_id)
    start = db.get(Episode, body.from_episode_id)
    if not s or not s.published or not start or start.series_id != series_id:
        raise HTTPException(404, "not_found")
    todo = [e for e in s.episodes if e.number >= start.number and not can_watch(db, user, e)][: body.count]
    if not todo:
        return {"unlocked": 0, "charged": 0, **wallet_out(user)}
    price = bundle_price(len(todo), s.coin_price)
    if user.coins_balance < price:
        raise HTTPException(402, {"error": "not_enough_coins", "need": price, "have": user.coins_balance})
    user.coins_balance -= price
    for e in todo:
        db.add(Unlock(user_id=user.id, episode_id=e.id, method="bundle"))
    db.add(Transaction(user_id=user.id, kind="unlock_bundle", coins_delta=-price))
    db.merge(user)
    db.commit()
    return {"unlocked": len(todo), "charged": price, **wallet_out(user)}


# ---------- колесо фортуни (лише віртуальні коїни, спіни не продаються) ----------
# (коїни, вага з 1000). Середній виграш = 13,3 коїна ≈ 0,67 серії. Шанси показуються користувачеві.
WHEEL = [(5, 150), (10, 280), (15, 180), (20, 100), (5, 150), (30, 60), (50, 30), (100, 10)]
_rng = secrets.SystemRandom()


def wheel_out(db: Session, user: User):
    free = free_spin_available(db, user)
    total = sum(w for _, w in WHEEL)
    return {"segments": [{"index": i, "coins": c, "odds_pct": round(w * 100 / total, 1)} for i, (c, w) in enumerate(WHEEL)],
            "free_available": free, "grants": grants_left(db, user), "spins": (1 if free else 0) + grants_left(db, user),
            "next_free_at": None if free else (now().replace(hour=0, minute=0, second=0, microsecond=0)
                                               + timedelta(days=1)).isoformat(),
            "rules": "Lucky Frame is free: 1 try per day plus extra tries for quests. Tries cannot be purchased. "
                     "Winnings are virtual in-app coins only; they cannot be withdrawn or exchanged for money."}


@app.get("/wheel")
def wheel_info(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return wheel_out(db, user)


@app.post("/wheel/spin")
def wheel_spin(db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = None
    if free_spin_available(db, user):
        source = "free"
    else:
        g = db.scalar(select(SpinGrant).where(SpinGrant.user_id == user.id, SpinGrant.used.is_(False))
                      .order_by(SpinGrant.id).limit(1))
        if g:
            g.used, source = True, "grant"
    if source is None:
        raise HTTPException(429, {"error": "no_spins", "next_free_at": wheel_out(db, user)["next_free_at"]})
    idx = _rng.choices(range(len(WHEEL)), weights=[w for _, w in WHEEL])[0]
    coins = WHEEL[idx][0]
    user.coins_balance += coins
    db.add(SpinLog(user_id=user.id, day=today(), source=source, segment=idx, coins=coins))
    db.add(Transaction(user_id=user.id, kind="wheel", coins_delta=coins))
    db.merge(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "retry")
    return {**wallet_out(user), "segment": idx, "won": coins, "wheel": wheel_out(db, user)}


# ---------- щоденні завдання ----------
# id: (назва, ціль, коїни, спіни, періодичність)
QUESTS = {
    "watch_3": ("Watch 3 episodes", 3, 10, 0, "daily"),
    "watch_10": ("Watch 10 episodes", 10, 25, 1, "daily"),
    "spin": ("Play Lucky Frame", 1, 5, 0, "daily"),
    "favorite": ("Add a series to My List", 1, 10, 0, "once"),
}


def quest_progress(db: Session, user: User, qid: str) -> int:
    day_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    if qid.startswith("watch"):
        return db.scalar(select(func.count(WatchProgress.id)).where(
            WatchProgress.user_id == user.id, WatchProgress.updated_at >= day_start, WatchProgress.position_sec >= 3)) or 0
    if qid == "spin":
        return db.scalar(select(func.count(SpinLog.id)).where(SpinLog.user_id == user.id, SpinLog.day == today())) or 0
    if qid == "favorite":
        return db.scalar(select(func.count(Favorite.id)).where(Favorite.user_id == user.id)) or 0
    return 0


def quest_day(qid: str) -> str:
    return "once" if QUESTS[qid][4] == "once" else today()


def quests_out(db: Session, user: User):
    out = []
    for qid, (title, target, coins, spins, kind) in QUESTS.items():
        claimed = db.scalar(select(QuestClaim.id).where(QuestClaim.user_id == user.id, QuestClaim.quest_id == qid,
                                                        QuestClaim.day == quest_day(qid))) is not None
        prog = min(quest_progress(db, user, qid), target)
        out.append({"id": qid, "title": title, "target": target, "progress": prog, "reward_coins": coins,
                    "reward_spins": spins, "kind": kind, "claimed": claimed, "claimable": prog >= target and not claimed})
    return out


@app.get("/quests")
def quests(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return quests_out(db, user)


@app.post("/quests/{quest_id}/claim")
def quest_claim(quest_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = next((x for x in quests_out(db, user) if x["id"] == quest_id), None)
    if not q:
        raise HTTPException(404, "quest_not_found")
    if q["claimed"]:
        raise HTTPException(409, "already_claimed")
    if not q["claimable"]:
        raise HTTPException(400, "not_completed")
    db.add(QuestClaim(user_id=user.id, quest_id=quest_id, day=quest_day(quest_id)))
    user.coins_balance += q["reward_coins"]
    for _ in range(q["reward_spins"]):
        db.add(SpinGrant(user_id=user.id, source=f"quest:{quest_id}"))
    db.add(Transaction(user_id=user.id, kind="quest", coins_delta=q["reward_coins"], product_id=quest_id))
    db.merge(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "already_claimed")
    return {**wallet_out(user), "reward_coins": q["reward_coins"], "reward_spins": q["reward_spins"], "quests": quests_out(db, user)}


# ---------- лайки серій ----------
@app.put("/episodes/{episode_id}/like")
def like_episode(episode_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Лайк. Перший лайк кожної серії дає 1 коїн (до 20 на добу); повторні лайки після зняття коїнів не дають."""
    ep = get_episode(db, episode_id)
    row = db.scalar(select(EpisodeLike).where(EpisodeLike.user_id == user.id, EpisodeLike.episode_id == ep.id))
    reward = 0
    if row is None:
        row = EpisodeLike(user_id=user.id, episode_id=ep.id, liked=True)
        db.add(row)
    else:
        row.liked = True
    if not row.rewarded and likes_today(db, user) < LIKE_DAILY_CAP:
        row.rewarded, reward = True, LIKE_REWARD
        user.coins_balance += reward
        db.add(Transaction(user_id=user.id, kind="like", coins_delta=reward, product_id=str(ep.id)))
        db.merge(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"liked": True, "reward": 0, **wallet_out(user)}
    total = db.scalar(select(func.count(EpisodeLike.id)).where(EpisodeLike.episode_id == ep.id, EpisodeLike.liked.is_(True)))
    return {"liked": True, "reward": reward, "likes": total, **wallet_out(user)}


@app.delete("/episodes/{episode_id}/like")
def unlike_episode(episode_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ep = get_episode(db, episode_id)
    row = db.scalar(select(EpisodeLike).where(EpisodeLike.user_id == user.id, EpisodeLike.episode_id == ep.id))
    if row:
        row.liked = False
        db.commit()
    total = db.scalar(select(func.count(EpisodeLike.id)).where(EpisodeLike.episode_id == ep.id, EpisodeLike.liked.is_(True)))
    return {"liked": False, "reward": 0, "likes": total, **wallet_out(user)}


# ---------- профіль і реферали ----------
REF_REFEREE_BONUS, REF_REFERRER_BONUS, REF_MAX = 20, 30, 20
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def get_profile(db: Session, user: User) -> Profile:
    p = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if p:
        return p
    for _ in range(10):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not db.scalar(select(Profile.id).where(Profile.ref_code == code)):
            break
    p = Profile(user_id=user.id, nickname="", ref_code=code)
    db.add(p)
    db.commit()
    return p


def profile_out(db: Session, user: User):
    p = get_profile(db, user)
    link = db.scalar(select(ReferralLink).where(ReferralLink.referee_id == user.id))
    invited = db.scalar(select(func.count(ReferralLink.id)).where(ReferralLink.referrer_id == user.id)) or 0
    earned = db.scalar(select(func.count(ReferralLink.id)).where(
        ReferralLink.referrer_id == user.id, ReferralLink.rewarded.is_(True))) or 0
    watched = db.scalar(select(func.count(WatchProgress.id)).where(
        WatchProgress.user_id == user.id, WatchProgress.position_sec >= 3)) or 0
    return {"user_id": user.id, "nickname": p.nickname, "display_name": p.nickname or f"Viewer #{user.id}",
            "ref_code": p.ref_code, "is_guest": True, "member_since": user.created_at.isoformat(),
            "episodes_watched": watched, "referred_by_set": link is not None, "invited": invited,
            "referral_rewards": earned * REF_REFERRER_BONUS,
            "referee_bonus": REF_REFEREE_BONUS, "referrer_bonus": REF_REFERRER_BONUS}


@app.get("/me/profile")
def me_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return profile_out(db, user)


class ProfileIn(BaseModel):
    nickname: str = Field(max_length=40)


@app.put("/me/profile")
def me_profile_update(body: ProfileIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = get_profile(db, user)
    p.nickname = " ".join(body.nickname.split())[:40]
    db.commit()
    return profile_out(db, user)


class RedeemIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)


@app.post("/referral/redeem")
def referral_redeem(body: RedeemIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Введення коду друга: ви отримуєте бонус одразу, друг — коли ви подивитесь 3 серії."""
    me = get_profile(db, user)
    code = body.code.strip().upper()
    ref = db.scalar(select(Profile).where(Profile.ref_code == code))
    if not ref:
        raise HTTPException(404, "code_not_found")
    if ref.user_id == user.id or code == me.ref_code:
        raise HTTPException(400, "own_code")
    if db.scalar(select(ReferralLink.id).where(ReferralLink.referee_id == user.id)):
        raise HTTPException(409, "already_redeemed")
    if (db.scalar(select(func.count(ReferralLink.id)).where(ReferralLink.referrer_id == ref.user_id)) or 0) >= REF_MAX:
        raise HTTPException(409, "code_limit_reached")
    db.add(ReferralLink(referee_id=user.id, referrer_id=ref.user_id))
    user.coins_balance += REF_REFEREE_BONUS
    db.add(Transaction(user_id=user.id, kind="referral", coins_delta=REF_REFEREE_BONUS, product_id="referee"))
    db.merge(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "already_redeemed")
    return {"reward_coins": REF_REFEREE_BONUS, **wallet_out(user)}


def settle_referral(db: Session, user: User):
    """Викликається з /progress: коли запрошений подивився 3 серії, запрошувач отримує бонус."""
    link = db.scalar(select(ReferralLink).where(ReferralLink.referee_id == user.id, ReferralLink.rewarded.is_(False)))
    if not link:
        return
    watched = db.scalar(select(func.count(WatchProgress.id)).where(
        WatchProgress.user_id == user.id, WatchProgress.position_sec >= 3)) or 0
    if watched < 3:
        return
    link.rewarded = True
    referrer = db.get(User, link.referrer_id)
    if referrer:
        referrer.coins_balance += REF_REFERRER_BONUS
        db.add(Transaction(user_id=referrer.id, kind="referral", coins_delta=REF_REFERRER_BONUS, product_id="referrer"))
    db.commit()


# ---------- оновлення застосунку ----------
@app.get("/app/version")
def app_version(code: int = 0, db: Session = Depends(get_db)):
    r = db.scalar(select(AppRelease).order_by(AppRelease.version_code.desc()).limit(1))
    if not r:
        return {"update_available": False}
    return {"update_available": r.version_code > code, "latest_code": r.version_code, "latest_name": r.version_name,
            "apk_url": r.apk_url, "notes": r.notes, "mandatory": r.mandatory and r.version_code > code}


class ReleaseIn(BaseModel):
    version_code: int = Field(ge=1)
    version_name: str
    apk_url: str
    notes: str = ""
    mandatory: bool = False


@app.post("/admin/app-release", dependencies=[Depends(admin_only)])
def admin_app_release(body: ReleaseIn, db: Session = Depends(get_db)):
    db.add(AppRelease(**body.model_dump()))
    db.commit()
    return {"ok": True}


# ---------- мови: субтитри та переклади каталогу ----------
@app.get("/episodes/{episode_id}/subtitles")
def list_subtitles(episode_id: int, db: Session = Depends(get_db)):
    get_episode(db, episode_id)
    rows = db.execute(select(EpisodeSubtitle.lang, EpisodeSubtitle.machine).where(EpisodeSubtitle.episode_id == episode_id)).all()
    return [{"lang": l, "machine": m, "url": f"/episodes/{episode_id}/subtitles/{l}.vtt"} for l, m in rows]


@app.get("/episodes/{episode_id}/subtitles/{lang}.vtt", response_class=PlainTextResponse)
def get_subtitle(episode_id: int, lang: str, db: Session = Depends(get_db)):
    get_episode(db, episode_id)
    row = db.scalar(select(EpisodeSubtitle).where(EpisodeSubtitle.episode_id == episode_id, EpisodeSubtitle.lang == lang))
    if not row:
        raise HTTPException(404, "subtitle_not_found")
    return PlainTextResponse(row.vtt, media_type="text/vtt; charset=utf-8")


class SubtitleIn(BaseModel):
    vtt: str = Field(min_length=6, max_length=200_000)
    machine: bool = True


@app.put("/admin/episodes/{episode_id}/subtitles/{lang}", dependencies=[Depends(admin_only)])
def admin_put_subtitle(episode_id: int, lang: str, body: SubtitleIn, db: Session = Depends(get_db)):
    if lang not in LANGS or not body.vtt.lstrip().startswith("WEBVTT"):
        raise HTTPException(422, "bad_lang_or_vtt")
    get_episode(db, episode_id)
    row = db.scalar(select(EpisodeSubtitle).where(EpisodeSubtitle.episode_id == episode_id, EpisodeSubtitle.lang == lang))
    if row:
        row.vtt, row.machine = body.vtt, body.machine
    else:
        db.add(EpisodeSubtitle(episode_id=episode_id, lang=lang, vtt=body.vtt, machine=body.machine))
    db.commit()
    return {"ok": True}


class SeriesTrIn(BaseModel):
    title: str = ""
    description: str = ""


@app.put("/admin/series/{series_id}/translations/{lang}", dependencies=[Depends(admin_only)])
def admin_put_series_tr(series_id: int, lang: str, body: SeriesTrIn, db: Session = Depends(get_db)):
    if lang not in LANGS or not db.get(Series, series_id):
        raise HTTPException(404, "not_found")
    row = db.scalar(select(SeriesTranslation).where(SeriesTranslation.series_id == series_id, SeriesTranslation.lang == lang))
    if row:
        row.title, row.description = body.title, body.description
    else:
        db.add(SeriesTranslation(series_id=series_id, lang=lang, title=body.title, description=body.description))
    db.commit()
    return {"ok": True}


@app.put("/admin/genres/{lang}", dependencies=[Depends(admin_only)])
def admin_put_genres(lang: str, body: dict[str, str], db: Session = Depends(get_db)):
    """Тіло: {"Драма": "Drama", ...} — переклад назв жанрів."""
    if lang not in LANGS:
        raise HTTPException(422, "bad_lang")
    for g, name in body.items():
        row = db.scalar(select(GenreTranslation).where(GenreTranslation.genre == g, GenreTranslation.lang == lang))
        if row:
            row.name = name
        else:
            db.add(GenreTranslation(genre=g, lang=lang, name=name))
    db.commit()
    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}
