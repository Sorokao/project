import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine

ADMIN = {"X-Admin-Key": "dev-admin-key"}


@pytest.fixture()
def c():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as cl:
        yield cl


def login(c, dev="device-0001"):
    t = c.post("/auth/guest", json={"device_id": dev}).json()["token"]
    return {"Authorization": f"Bearer {t}"}


def seed(c, free=2, price=20, eps=4):
    sid = c.post("/admin/series", json={"title": "T", "free_episodes": free, "coin_price": price}, headers=ADMIN).json()["id"]
    ids = [c.post("/admin/episodes", json={"series_id": sid, "number": n, "video_url": f"http://v/{n}.mp4"},
                  headers=ADMIN).json()["id"] for n in range(1, eps + 1)]
    return sid, ids


def test_guest_is_stable_and_me(c):
    a = c.post("/auth/guest", json={"device_id": "device-0001"}).json()["user_id"]
    b = c.post("/auth/guest", json={"device_id": "device-0001"}).json()["user_id"]
    assert a == b
    assert c.get("/me", headers=login(c)).json()["coins"] == 0
    assert c.get("/me").status_code == 401


def test_admin_requires_key(c):
    assert c.post("/admin/series", json={"title": "x"}).status_code == 403


def test_free_then_locked_then_unlock(c):
    h = login(c)
    sid, ids = seed(c)
    assert c.get(f"/episodes/{ids[0]}/play", headers=h).status_code == 200
    r = c.get(f"/episodes/{ids[2]}/play", headers=h)
    assert r.status_code == 402
    assert c.post(f"/episodes/{ids[2]}/unlock", headers=h).status_code == 402  # немає коїнів
    c.post("/billing/verify", json={"product_id": "coins_499", "purchase_token": "mock-aaaa"}, headers=h)
    r = c.post(f"/episodes/{ids[2]}/unlock", headers=h).json()
    assert r["charged"] == 20 and r["coins"] == 680   # 600 + 100 бонус першої покупки
    assert c.get(f"/episodes/{ids[2]}/play", headers=h).status_code == 200
    again = c.post(f"/episodes/{ids[2]}/unlock", headers=h).json()
    assert again["charged"] == 0 and again["coins"] == 680
    lst = c.get(f"/series/{sid}/episodes", headers=h).json()
    assert [e["locked"] for e in lst] == [False, False, False, True]


def test_play_returns_next_episode(c):
    h = login(c)
    _, ids = seed(c)
    j = c.get(f"/episodes/{ids[0]}/play", headers=h).json()
    assert j["next_episode_id"] == ids[1]


def test_daily_bonus_and_streak(c):
    h = login(c)
    r = c.post("/wallet/daily-bonus", headers=h).json()
    assert r["bonus"] == 5 and r["coins"] == 5
    assert c.post("/wallet/daily-bonus", headers=h).status_code == 429


def test_billing_idempotent_and_validation(c):
    h = login(c)
    ok = {"product_id": "coins_999", "purchase_token": "mock-bbbb"}
    assert c.post("/billing/verify", json=ok, headers=h).json()["coins"] == 1400
    d = c.post("/billing/verify", json=ok, headers=h).json()
    assert d["duplicate"] and d["coins"] == 1400
    assert c.post("/billing/verify", json={"product_id": "coins_999", "purchase_token": "real-xx"}, headers=h).status_code == 400
    assert c.post("/billing/verify", json={"product_id": "nope", "purchase_token": "mock-cccc"}, headers=h).status_code == 400


def test_vip_unlocks_everything_and_extends(c):
    h = login(c)
    _, ids = seed(c)
    j = c.post("/billing/verify", json={"product_id": "vip_week", "purchase_token": "mock-dddd"}, headers=h).json()
    assert j["vip"]
    assert c.get(f"/episodes/{ids[3]}/play", headers=h).status_code == 200
    j2 = c.post("/billing/verify", json={"product_id": "vip_week", "purchase_token": "mock-eeee"}, headers=h).json()
    assert j2["vip_until"] > j["vip_until"]


def test_unpublished_hidden_and_progress(c):
    h = login(c)
    sid, ids = seed(c)
    assert c.post("/progress", json={"episode_id": ids[0], "position_sec": 12}, headers=h).json()["ok"]
    c.patch(f"/admin/series/{sid}", json={"published": False}, headers=ADMIN)
    assert c.get("/series").json() == []
    assert c.get(f"/episodes/{ids[0]}/play", headers=h).status_code == 404


def test_duplicate_episode_number(c):
    sid, _ = seed(c, eps=1)
    r = c.post("/admin/episodes", json={"series_id": sid, "number": 1, "video_url": "x"}, headers=ADMIN)
    assert r.status_code == 409


def test_admin_patch_episode(c):
    _, ids = seed(c, eps=1)
    assert c.patch(f"/admin/episodes/{ids[0]}", json={"video_url": "http://x/new.mp4"}).status_code == 403
    r = c.patch(f"/admin/episodes/{ids[0]}", json={"video_url": "http://x/new.mp4"}, headers=ADMIN)
    assert r.json()["video_url"] == "http://x/new.mp4"
    assert c.patch("/admin/episodes/9999", json={}, headers=ADMIN).status_code == 404


def test_static_video_served_with_range(c):
    r = c.get("/static/videos/demo_space.mp4", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100


def test_wallet_bonus_state_and_streak_fields(c):
    h = login(c)
    w = c.get("/wallet", headers=h).json()
    assert w["bonus_available"] and w["next_bonus"] == 5
    c.post("/wallet/daily-bonus", headers=h)
    w = c.get("/wallet", headers=h).json()
    assert not w["bonus_available"] and w["next_bonus_at"] and w["bonus_streak"] == 1


def test_search_and_genre(c):
    c.post("/admin/series", json={"title": "Нічна зміна", "genre": "Трилер"}, headers=ADMIN)
    c.post("/admin/series", json={"title": "Спадкоємиця", "genre": "Романтика"}, headers=ADMIN)
    assert [x["title"] for x in c.get("/series", params={"q": "ніч"}).json()] == ["Нічна зміна"]
    assert [x["title"] for x in c.get("/series", params={"genre": "Романтика"}).json()] == ["Спадкоємиця"]


def test_favorites_roundtrip(c):
    h = login(c)
    sid, _ = seed(c, eps=1)
    assert c.get("/me/favorites", headers=h).json() == []
    assert c.put(f"/me/favorites/{sid}", headers=h).json()["favorite"]
    c.put(f"/me/favorites/{sid}", headers=h)  # ідемпотентно
    assert [x["id"] for x in c.get("/me/favorites", headers=h).json()] == [sid]
    c.delete(f"/me/favorites/{sid}", headers=h)
    assert c.get("/me/favorites", headers=h).json() == []


def test_home_and_continue(c):
    h = login(c)
    sid, ids = seed(c)
    c.post("/progress", json={"episode_id": ids[1], "position_sec": 5}, headers=h)
    j = c.get("/home", headers=h).json()
    assert j["continue_watching"][0]["episode_number"] == 2
    assert [r["title"] for r in j["rows"]][:2] == ["Новинки", "Популярне"]
    assert j["featured"][0]["id"] == sid


def test_bundle_unlock_discount(c):
    h = login(c)
    sid, ids = seed(c, free=1, price=20, eps=5)
    c.post("/billing/verify", json={"product_id": "coins_499", "purchase_token": "mock-bundle1"}, headers=h)
    r = c.post(f"/series/{sid}/unlock-bundle", json={"from_episode_id": ids[1], "count": 3}, headers=h).json()
    assert r["unlocked"] == 3 and r["charged"] == 54 and r["coins"] == 646   # 3*20*0.9
    eps = c.get(f"/series/{sid}/episodes", headers=h).json()
    assert [e["locked"] for e in eps] == [False, False, False, False, True]
    assert c.post(f"/series/{sid}/unlock-bundle", json={"from_episode_id": ids[0], "count": 1}, headers=h).json()["unlocked"] == 1


def buy(c, h, pid, tok):
    return c.post("/billing/verify", json={"product_id": pid, "purchase_token": tok}, headers=h).json()


def test_first_purchase_bonus_once_and_starter_triple(c):
    h = login(c)
    assert c.get("/wallet", headers=h).json()["first_purchase_available"] is True
    r = buy(c, h, "coins_099", "mock-starter1")
    assert r["coins"] == 300 and r["first_bonus"] == 200 and r["first_purchase_available"] is False
    r = buy(c, h, "coins_099", "mock-starter2")
    assert r["coins"] == 400 and r["first_bonus"] == 0          # бонус лише раз
    h2 = login(c, "device-0002")
    assert buy(c, h2, "coins_499", "mock-first2")["coins"] == 700   # 600 + 100
    h3 = login(c, "device-0003")
    assert buy(c, h3, "vip_week", "mock-vipx")["first_purchase_available"] is True  # VIP не рахується як покупка коїнів


def test_bundle_tiers_and_options(c):
    h = login(c)
    sid, ids = seed(c, free=1, price=20, eps=30)
    opts = c.get(f"/series/{sid}/bundles", params={"from_episode_id": ids[1]}, headers=h).json()
    assert [o["count"] for o in opts] == [1, 5, 29]
    assert opts[1]["price"] == 85 and opts[1]["discount_pct"] == 15      # 100 * 0.85
    assert opts[2]["all"] and opts[2]["price"] == round(29 * 20 * 0.65) and opts[2]["discount_pct"] == 35
    buy(c, h, "coins_999", "mock-bigpack")
    r = c.post(f"/series/{sid}/unlock-bundle", json={"from_episode_id": ids[1], "count": 29}, headers=h).json()
    assert r["unlocked"] == 29 and r["charged"] == 377
    assert all(not e["locked"] for e in c.get(f"/series/{sid}/episodes", headers=h).json())


def test_wheel_free_daily_and_odds(c):
    h = login(c)
    w = c.get("/wheel", headers=h).json()
    assert w["free_available"] and w["spins"] == 1 and len(w["segments"]) == 8
    assert abs(sum(s["odds_pct"] for s in w["segments"]) - 100) < 0.2 and "не можна вивести" in w["rules"]
    r = c.post("/wheel/spin", headers=h).json()
    assert r["coins"] == w["segments"][r["segment"]]["coins"] and r["coins"] in (5, 10, 15, 20, 30, 50, 100)
    assert r["coins"] == c.get("/wallet", headers=h).json()["coins"]
    assert r["wheel"]["free_available"] is False
    j = c.post("/wheel/spin", headers=h)
    assert j.status_code == 429 and j.json()["detail"]["error"] == "no_spins"


def test_wheel_expected_value():
    from app.main import WHEEL
    ev = sum(c * w for c, w in WHEEL) / sum(w for _, w in WHEEL)
    assert 12 <= ev <= 15


def test_quests_flow_and_grant_spin(c):
    h = login(c)
    sid, ids = seed(c, free=20, eps=12)
    qs = {q["id"]: q for q in c.get("/quests", headers=h).json()}
    assert not qs["watch_3"]["claimable"] and qs["watch_3"]["progress"] == 0
    assert c.post("/quests/watch_3/claim", headers=h).status_code == 400
    for i in ids[:10]:
        c.post("/progress", json={"episode_id": i, "position_sec": 8}, headers=h)
    qs = {q["id"]: q for q in c.get("/quests", headers=h).json()}
    assert qs["watch_3"]["claimable"] and qs["watch_10"]["claimable"]
    r = c.post("/quests/watch_3/claim", headers=h).json()
    assert r["reward_coins"] == 10 and r["coins"] == 10 == c.get("/wallet", headers=h).json()["coins"]
    assert c.post("/quests/watch_3/claim", headers=h).status_code == 409
    c.post("/quests/watch_10/claim", headers=h)          # +25 коїнів і +1 спін
    assert c.get("/wheel", headers=h).json()["grants"] == 1
    c.post("/wheel/spin", headers=h); c.post("/wheel/spin", headers=h)  # безкоштовний + виданий
    assert c.post("/wheel/spin", headers=h).status_code == 429
    c.put(f"/me/favorites/{sid}", headers=h)
    assert c.post("/quests/favorite/claim", headers=h).json()["reward_coins"] == 10
    assert c.post("/quests/favorite/claim", headers=h).status_code == 409
    assert c.post("/quests/nope/claim", headers=h).status_code == 404
