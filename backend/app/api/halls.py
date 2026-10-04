from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import DamagedSeat, Hall
from app.services.seat_engine import SeatingError, normalize_damaged
router = APIRouter(prefix="/halls", tags=["halls"])

@router.get("")
def list_halls(db: Session = Depends(get_db)):
    return [{"id": r.id, "code": r.code, "name": r.name, "rows": r.rows, "cols": r.cols, "min_manhattan": r.min_manhattan}
            for r in db.scalars(select(Hall).order_by(Hall.id)).all()]

class DamagedIn(BaseModel):
    seats: list[dict]

def load_damaged(db: Session, hall_id: int) -> frozenset[tuple[int, int]]:
    rows = db.scalars(select(DamagedSeat).where(DamagedSeat.hall_id == hall_id)).all()
    return frozenset((r.row, r.col) for r in rows)

@router.get("/{hall_id}/damaged")
def get_damaged(hall_id: int, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall: raise HTTPException(404, "考室不存在")
    seats = sorted(load_damaged(db, hall_id))
    return {"hall_id": hall_id, "seats": [{"row": r, "col": c} for r, c in seats]}

@router.put("/{hall_id}/damaged")
def set_damaged(hall_id: int, body: DamagedIn, db: Session = Depends(get_db)):
    """保存当下损坏名单（满格时传空名单）。

    行列越界或重复登记整场拒绝：先校验后落库，名单、最新方案、统计停在拒绝前。
    """
    hall = db.get(Hall, hall_id)
    if not hall: raise HTTPException(404, "考室不存在")
    try:
        normalized = normalize_damaged(hall.rows, hall.cols, body.seats)
    except SeatingError as e:
        raise HTTPException(400, str(e))
    for r in db.scalars(select(DamagedSeat).where(DamagedSeat.hall_id == hall_id)).all():
        db.delete(r)
    for r, c in sorted(normalized):
        db.add(DamagedSeat(hall_id=hall_id, row=r, col=c))
    db.commit()
    return {"hall_id": hall_id, "seats": [{"row": r, "col": c} for r, c in sorted(normalized)]}
