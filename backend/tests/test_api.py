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
    assert r["charged"] == 20 and r["coins"] == 480
    assert c.get(f"/episodes/{ids[2]}/play", headers=h).status_code == 200
    again = c.post(f"/episodes/{ids[2]}/unlock", headers=h).json()
    assert again["charged"] == 0 and again["coins"] == 480
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
    assert c.post("/billing/verify", json=ok, headers=h).json()["coins"] == 1100
    d = c.post("/billing/verify", json=ok, headers=h).json()
    assert d["duplicate"] and d["coins"] == 1100
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
