import os

os.environ["DATABASE_URL"] = "sqlite:///./_test_damaged_api.db"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models.models import DamagedSeat, SeatPlan
from app.services.seed import seed_if_empty

Base.metadata.create_all(bind=engine)
_db = SessionLocal()
try:
    seed_if_empty(_db)
finally:
    _db.close()

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_tables():
    db = SessionLocal()
    try:
        db.execute(delete(DamagedSeat))
        db.execute(delete(SeatPlan))
        db.commit()
    finally:
        db.close()
    yield


def _plans():
    return client.get("/api/seating/plans?hall_id=1").json()


def test_seed_corner_damage_then_split_fails():
    # 仅坏第 0 行第 0 列：仍连通可排，该格无人，容量 29
    r = client.put("/api/damaged?hall_id=1", json={"cells": [{"row": 0, "col": 0}]})
    assert r.status_code == 200
    assert r.json()["capacity"] == 29
    assert r.json()["connected"] is True
    r = client.post("/api/seating/run?hall_id=1")
    assert r.status_code == 200
    data = r.json()
    assert data["stats"]["capacity"] == 29
    assert data["stats"]["damaged"] == 1
    assert data["damaged"] == [{"row": 0, "col": 0}]
    assert all(not (a["row"] == 0 and a["col"] == 0) for a in data["assignments"])
    n_plans = len(_plans())
    assert n_plans >= 1
    # 再坏到把房间割开：整场失败且方案列表不增行
    r = client.put(
        "/api/damaged?hall_id=1",
        json={"cells": [{"row": 0, "col": 0}, {"row": 0, "col": 2}, {"row": 1, "col": 1}]},
    )
    assert r.status_code == 200
    assert r.json()["connected"] is False
    r = client.post("/api/seating/run?hall_id=1")
    assert r.status_code == 409
    assert r.json()["detail"] == "损坏后考室不连通"
    assert "非法" not in r.json()["detail"]
    assert "行列" not in r.json()["detail"]
    assert len(_plans()) == n_plans


def test_out_of_bounds_rejected_atomically():
    client.put("/api/damaged?hall_id=1", json={"cells": [{"row": 1, "col": 1}]})
    run = client.post("/api/seating/run?hall_id=1")
    assert run.status_code == 200
    stats_before = client.get("/api/seating/stats?hall_id=1").json()
    plans_before = _plans()
    for bad in ({"row": 5, "col": 0}, {"row": 0, "col": 6}, {"row": -1, "col": 0}, {"row": 0, "col": -1}):
        r = client.put("/api/damaged?hall_id=1", json={"cells": [bad]})
        assert r.status_code == 400
        assert "非法" in r.json()["detail"]
    # 名单、最新方案、统计停在拒绝前
    assert client.get("/api/damaged?hall_id=1").json()["damaged"] == [{"row": 1, "col": 1}]
    assert _plans() == plans_before
    assert client.get("/api/seating/stats?hall_id=1").json() == stats_before


def test_duplicate_rejected_atomically():
    r = client.put("/api/damaged?hall_id=1",
                   json={"cells": [{"row": 2, "col": 2}, {"row": 2, "col": 2}]})
    assert r.status_code == 400
    assert "重复" in r.json()["detail"]
    assert client.get("/api/damaged?hall_id=1").json()["damaged"] == []


def test_mixed_valid_and_invalid_rejected_atomically():
    # 一个越界格子拖垮整单：合法格子也不许落库
    r = client.put("/api/damaged?hall_id=1",
                   json={"cells": [{"row": 0, "col": 0}, {"row": 9, "col": 9}]})
    assert r.status_code == 400
    assert client.get("/api/damaged?hall_id=1").json()["damaged"] == []


def test_clear_restores_full_grid():
    client.put("/api/damaged?hall_id=1", json={"cells": [{"row": 0, "col": 0}]})
    r = client.put("/api/damaged?hall_id=1", json={"cells": []})
    assert r.status_code == 200
    assert r.json()["capacity"] == 30
    assert r.json()["connected"] is True
    r = client.post("/api/seating/run?hall_id=1")
    assert r.status_code == 200
    assert r.json()["stats"]["capacity"] == 30
    assert r.json()["stats"]["damaged"] == 0
    assert r.json()["damaged"] == []


def test_reseat_uses_saved_damage_list():
    client.put("/api/damaged?hall_id=1", json={"cells": [{"row": 0, "col": 0}]})
    r = client.post("/api/seating/run?hall_id=1")
    assert r.status_code == 200
    assert all(not (a["row"] == 0 and a["col"] == 0) for a in r.json()["assignments"])
    latest = client.get("/api/seating/latest?hall_id=1").json()
    assert latest["damaged"] == [{"row": 0, "col": 0}]
    assert all(not (a["row"] == 0 and a["col"] == 0) for a in latest["assignments"])
    # 改名单后再排：必须按新名单出图
    client.put("/api/damaged?hall_id=1", json={"cells": [{"row": 4, "col": 5}]})
    r = client.post("/api/seating/run?hall_id=1")
    assert r.status_code == 200
    assert r.json()["damaged"] == [{"row": 4, "col": 5}]
    assert all(not (a["row"] == 4 and a["col"] == 5) for a in r.json()["assignments"])


def test_unplaced_reason_not_spacing_when_damage_squeezes_capacity():
    cells = [{"row": r, "col": c} for r in range(5) for c in range(4)]
    r = client.put("/api/damaged?hall_id=1", json={"cells": cells})
    assert r.json()["capacity"] == 10
    assert r.json()["connected"] is True
    r = client.post("/api/seating/run?hall_id=1")
    assert r.status_code == 200
    data = r.json()
    assert data["stats"]["unplaced"] > 0
    for u in data["unplaced"]:
        assert "间距" not in u["reason"]
        assert "同卷" not in u["reason"]
        assert "损坏" in u["reason"]
    # 同一套容量账：图、统计、未排名单互相对得上
    assert data["stats"]["capacity"] == 10
    assert len(data["damaged"]) == 20
    assert data["stats"]["seated"] + data["stats"]["unplaced"] == 12
    assert data["stats"]["seated"] <= data["stats"]["capacity"]


def test_stats_track_latest_plan_capacity():
    client.put("/api/damaged?hall_id=1", json={"cells": [{"row": 0, "col": 0}]})
    client.post("/api/seating/run?hall_id=1")
    s = client.get("/api/seating/stats?hall_id=1").json()
    assert s["capacity"] == 29
    assert s["damaged"] == 1
    assert s["capacity_total"] == 30
