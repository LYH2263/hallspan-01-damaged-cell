import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Candidate, DamagedSeat, Hall, SeatPlan
from app.services.seat_engine import (
    SeatingError, assert_connected, find_violations, normalize_damaged,
    place_candidates, plan_to_dict,
)
router = APIRouter(prefix="/seating", tags=["seating"])

def load_damaged(db: Session, hall_id: int, hall: Hall) -> frozenset[tuple[int, int]]:
    raw = [{"row": r.row, "col": r.col}
           for r in db.scalars(select(DamagedSeat).where(DamagedSeat.hall_id == hall_id)).all()]
    # 落库名单理论上合法；再校验一次，保证容量账与名单同源
    return normalize_damaged(hall.rows, hall.cols, raw)

def build_plan(db: Session, hall: Hall) -> dict:
    """按保存当下的损坏名单出图。割裂时整场失败（SeatingError），不落任何方案行。"""
    hall_id = hall.id
    damaged = load_damaged(db, hall_id, hall)
    assert_connected(hall.rows, hall.cols, damaged)
    cands = [{"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
             for c in db.scalars(select(Candidate).where(Candidate.hall_id == hall_id)).all()]
    assigns, unplaced = place_candidates(hall.rows, hall.cols, hall.min_manhattan, cands, damaged)
    viols = find_violations(hall.rows, hall.cols, hall.min_manhattan, assigns)
    result = plan_to_dict(assigns, unplaced, viols, hall.rows, hall.cols, damaged)
    # 容量账守卫：图、统计、未排名单必须对同一套账，对不齐整场失败
    assert result["stats"]["seated"] + result["stats"]["unplaced"] == len(cands)
    assert result["stats"]["capacity"] == hall.rows * hall.cols - len(damaged)
    assert all((a["row"], a["col"]) not in damaged for a in result["assignments"])
    result["hall"] = {"id": hall.id, "name": hall.name, "min_manhattan": hall.min_manhattan}
    return result

@router.post("/run")
def run_seating(hall_id: int = 1, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall: raise HTTPException(404, "考室不存在")
    try:
        result = build_plan(db, hall)
    except SeatingError as e:
        # 割裂只写不连通，不与非法行列并句；方案列表不增行
        raise HTTPException(409, str(e))
    plan = SeatPlan(hall_id=hall_id, created_at=datetime.utcnow(), result_json=json.dumps(result, ensure_ascii=False))
    db.add(plan); db.commit(); db.refresh(plan)
    return {"id": plan.id, **result}

def _damaged_sig(data: dict) -> set[tuple[int, int]]:
    return {(d["row"], d["col"]) for d in data.get("damaged", [])}

@router.get("/latest")
def latest(hall_id: int = 1, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall: raise HTTPException(404, "考室不存在")
    plan = db.scalars(select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id.desc())).first()
    current = {(r.row, r.col)
               for r in db.scalars(select(DamagedSeat).where(DamagedSeat.hall_id == hall_id)).all()}
    if not plan:
        return run_seating(hall_id=hall_id, db=db)
    data = json.loads(plan.result_json)
    if _damaged_sig(data) != current:
        # 损坏名单刚改：禁止继续展示占用损坏格的旧座位，按保存当下名单即时重算（不增方案行）
        try:
            result = build_plan(db, hall)
        except SeatingError as e:
            raise HTTPException(409, str(e))
        return {"id": plan.id, **result}
    return {"id": plan.id, **data}

@router.get("/violations")
def violations(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, "violations": data.get("violations", []), "unplaced": data.get("unplaced", [])}

@router.get("/stats")
def stats(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, **data.get("stats", {})}
