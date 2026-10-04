import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Candidate, DamagedSeat, Hall, SeatPlan
from app.services.seat_engine import (
    CapacityMismatchError,
    find_violations,
    is_connected,
    place_candidates,
    plan_to_dict,
    reconcile_plan,
)
router = APIRouter(prefix="/seating", tags=["seating"])

def _damaged_set(db: Session, hall_id: int) -> set[tuple[int, int]]:
    return {(d.row, d.col)
            for d in db.scalars(select(DamagedSeat).where(DamagedSeat.hall_id == hall_id)).all()}

@router.post("/run")
def run_seating(hall_id: int = 1, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall: raise HTTPException(404, "考室不存在")
    damaged = _damaged_set(db, hall_id)
    # 损坏把可坐区域割成互不四邻连通的两块 → 整场失败，方案列表不增行
    if not is_connected(hall.rows, hall.cols, damaged):
        raise HTTPException(409, "损坏后考室不连通")
    cands = [{"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
             for c in db.scalars(select(Candidate).where(Candidate.hall_id == hall_id)).all()]
    assigns, unplaced = place_candidates(hall.rows, hall.cols, hall.min_manhattan, cands, damaged)
    viols = find_violations(hall.rows, hall.cols, hall.min_manhattan, assigns)
    result = plan_to_dict(assigns, unplaced, viols, hall.rows, hall.cols, damaged)
    result["hall"] = {"id": hall.id, "name": hall.name, "min_manhattan": hall.min_manhattan}
    try:
        reconcile_plan(result, hall.rows, hall.cols, damaged, len(cands))
    except CapacityMismatchError as exc:
        db.rollback()
        raise HTTPException(500, f"容量账对不齐，整场失败：{exc}")
    plan = SeatPlan(hall_id=hall_id, created_at=datetime.utcnow(), result_json=json.dumps(result, ensure_ascii=False))
    db.add(plan); db.commit(); db.refresh(plan)
    return {"id": plan.id, **result}

@router.get("/plans")
def plans(hall_id: int = 1, db: Session = Depends(get_db)):
    rows = db.scalars(select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id)).all()
    return [{"id": p.id, "hall_id": p.hall_id, "created_at": p.created_at.isoformat() if p.created_at else None}
            for p in rows]

@router.get("/latest")
def latest(hall_id: int = 1, db: Session = Depends(get_db)):
    plan = db.scalars(select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id.desc())).first()
    if not plan:
        return run_seating(hall_id=hall_id, db=db)
    data = json.loads(plan.result_json)
    return {"id": plan.id, **data}

@router.get("/violations")
def violations(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, "violations": data.get("violations", []), "unplaced": data.get("unplaced", [])}

@router.get("/stats")
def stats(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, **data.get("stats", {})}
