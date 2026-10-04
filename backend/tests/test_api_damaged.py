"""端到端：损坏名单保存、越界/重复拒绝、割裂失败不增方案行、容量账联动。

依赖 FastAPI TestClient（httpx），在容器 `pytest` 下运行；用内存 SQLite 覆盖 get_db。
"""
import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SEED_ON_EMPTY"] = "false"
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
import app.database as dbmod
import app.main as mainmod
from app.main import app
from app.models.models import Candidate, Hall, PaperSet, SeatPlan

# 共享同一个内存 SQLite（StaticPool 单连接），app 生命周期与测试会话共用一套表
test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=test_engine, autoflush=False)
dbmod.engine = test_engine
dbmod.SessionLocal = TestingSession
mainmod.engine = test_engine
mainmod.SessionLocal = TestingSession
Base.metadata.create_all(test_engine)

def _override_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = _override_db
client = TestClient(app)

@pytest.fixture()
def hall():
    db = TestingSession()
    h = Hall(code="H1", name="测试考室", rows=5, cols=6, min_manhattan=2)
    db.add(h); db.flush()
    p = PaperSet(code="PA", title="A卷"); db.add(p); db.flush()
    for i in range(12):
        db.add(Candidate(hall_id=h.id, name=f"考生{i}", ticket_no=f"T{i}", paper_id=p.id))
    db.commit()
    hid = h.id
    db.close()
    yield hid
    db = TestingSession()
    for m in (SeatPlan, Candidate, PaperSet, Hall):
        db.query(m).delete()
    db.commit(); db.close()

def plan_count(hid):
    db = TestingSession()
    n = len(db.scalars(select(SeatPlan).where(SeatPlan.hall_id == hid)).all())
    db.close(); return n

def test_origin_damage_runs_capacity_29(hall):
    r = client.put(f"/api/halls/{hall}/damaged", json={"seats": [{"row": 0, "col": 0}]})
    assert r.status_code == 200
    r = client.post(f"/api/seating/run", params={"hall_id": hall})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["stats"]["capacity"] == 29
    assert data["stats"]["damaged"] == 1
    assert all(not (a["row"] == 0 and a["col"] == 0) for a in data["assignments"])
    assert plan_count(hall) == 1

def test_disconnected_damage_fails_without_new_plan(hall):
    client.put(f"/api/halls/{hall}/damaged", json={"seats": [{"row": 0, "col": 0}]})
    client.post(f"/api/seating/run", params={"hall_id": hall})
    assert plan_count(hall) == 1
    cut = [{"row": r, "col": 2} for r in range(5)]
    r = client.put(f"/api/halls/{hall}/damaged", json={"seats": cut})
    assert r.status_code == 200
    r = client.post(f"/api/seating/run", params={"hall_id": hall})
    assert r.status_code == 409
    assert "不连通" in r.text and "越界" not in r.text
    # 割裂仍排互斥：方案列表不增行
    assert plan_count(hall) == 1
    # stats/latest 同样失败，不偷偷分区排座
    assert client.get("/api/seating/stats", params={"hall_id": hall}).status_code == 409

def test_out_of_bounds_and_duplicate_rejected_state_unchanged(hall):
    client.put(f"/api/halls/{hall}/damaged", json={"seats": [{"row": 0, "col": 0}]})
    r = client.put(f"/api/halls/{hall}/damaged",
                   json={"seats": [{"row": 5, "col": 0}]})
    assert r.status_code == 400 and "越界" in r.text
    r = client.put(f"/api/halls/{hall}/damaged",
                   json={"seats": [{"row": 1, "col": 1}, {"row": 1, "col": 1}]})
    assert r.status_code == 400 and "重复" in r.text
    # 名单停在拒绝前
    got = client.get(f"/api/halls/{hall}/damaged").json()["seats"]
    assert got == [{"row": 0, "col": 0}]

def test_clear_list_restores_full_capacity(hall):
    client.put(f"/api/halls/{hall}/damaged", json={"seats": [{"row": 0, "col": 0}]})
    r = client.put(f"/api/halls/{hall}/damaged", json={"seats": []})
    assert r.status_code == 200
    r = client.post(f"/api/seating/run", params={"hall_id": hall})
    assert r.json()["stats"]["capacity"] == 30

def test_rerun_after_list_change_uses_saved_list(hall):
    client.put(f"/api/halls/{hall}/damaged", json={"seats": [{"row": 0, "col": 0}]})
    client.post(f"/api/seating/run", params={"hall_id": hall})
    # 刚改名单未重新排：latest 必须按保存当下名单出图，不展示旧账
    client.put(f"/api/halls/{hall}/damaged", json={"seats": [{"row": 4, "col": 5}]})
    data = client.get("/api/seating/latest", params={"hall_id": hall}).json()
    cur = {(d["row"], d["col"]) for d in data["damaged"]}
    assert cur == {(4, 5)}
    assert data["stats"]["capacity"] == 29
    assert all((a["row"], a["col"]) not in cur for a in data["assignments"])
