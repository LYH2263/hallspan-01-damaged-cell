from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import DamagedSeat, Hall
from app.services.seat_engine import is_connected

router = APIRouter(prefix="/damaged", tags=["damaged"])


class CellIn(BaseModel):
    row: int
    col: int


class DamagedIn(BaseModel):
    cells: list[CellIn]


def _payload(db: Session, hall: Hall) -> dict:
    cells = sorted(
        (d.row, d.col)
        for d in db.scalars(select(DamagedSeat).where(DamagedSeat.hall_id == hall.id)).all()
    )
    return {
        "hall_id": hall.id,
        "rows": hall.rows,
        "cols": hall.cols,
        "damaged": [{"row": r, "col": c} for r, c in cells],
        "damaged_count": len(cells),
        "capacity": hall.rows * hall.cols - len(cells),
        "connected": is_connected(hall.rows, hall.cols, cells),
    }


@router.get("")
def get_damaged(hall_id: int = 1, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    return _payload(db, hall)


@router.put("")
def put_damaged(body: DamagedIn, hall_id: int = 1, db: Session = Depends(get_db)):
    """整单替换损坏格名单。任一格子行列越界或重复登记 → 整场拒绝，名单保持原样。"""
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    seen: set[tuple[int, int]] = set()
    for cell in body.cells:
        if not (0 <= cell.row < hall.rows and 0 <= cell.col < hall.cols):
            raise HTTPException(400, f"损坏格行列非法：第 {cell.row} 行第 {cell.col} 列越界，整场拒绝")
        if (cell.row, cell.col) in seen:
            raise HTTPException(400, f"损坏格重复登记：第 {cell.row} 行第 {cell.col} 列，整场拒绝")
        seen.add((cell.row, cell.col))
    db.execute(delete(DamagedSeat).where(DamagedSeat.hall_id == hall.id))
    for r, c in sorted(seen):
        db.add(DamagedSeat(hall_id=hall.id, row=r, col=c))
    db.commit()
    return _payload(db, hall)
