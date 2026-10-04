"""Exam seating: min Manhattan distance; same paper_id cannot be 4-neighbor adjacent.

损坏格（damaged）禁止落人。排座只允许在「剩余可坐格四邻连通」时进行：
损坏把可坐区域割成多个互不四邻连通的分量时，整场排座失败（SeatingError，
不产生任何方案行）。排座图、容量统计、未排名单共用同一套容量账：
capacity = rows * cols - len(damaged)。
"""
from __future__ import annotations
from dataclasses import asdict, dataclass

@dataclass
class SeatAssign:
    candidate_id: int
    name: str
    ticket_no: str
    paper_id: int
    row: int
    col: int

@dataclass
class Violation:
    kind: str
    a_id: int
    b_id: int
    detail: str

class SeatingError(ValueError):
    """整场拒绝：损坏名单非法（越界/重复），或损坏后可坐格不连通。"""

def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def neighbors4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out

def seatable_cells(rows: int, cols: int, damaged: frozenset[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in damaged]

def normalize_damaged(rows: int, cols: int, damaged: list[dict] | list[tuple[int, int]]) -> frozenset[tuple[int, int]]:
    """校验损坏名单：行列越界或重复登记整场拒绝；返回去重后的集合。"""
    seen: set[tuple[int, int]] = set()
    for item in damaged:
        if isinstance(item, dict):
            r, c = item.get("row"), item.get("col")
        else:
            r, c = item
        if not isinstance(r, int) or not isinstance(c, int) or isinstance(r, bool) or isinstance(c, bool) \
                or not (0 <= r < rows and 0 <= c < cols):
            raise SeatingError(f"损坏格行列越界：第 {r} 行第 {c} 列不在 {rows}×{cols} 考室内")
        if (r, c) in seen:
            raise SeatingError(f"损坏格重复登记：第 {r} 行第 {c} 列")
        seen.add((r, c))
    return frozenset(seen)

def assert_connected(rows: int, cols: int, damaged: frozenset[tuple[int, int]]) -> None:
    """可坐格被损坏割成两块及以上即整场失败；说明只写不连通，不与非法行列并句。"""
    cells = set(seatable_cells(rows, cols, damaged))
    if not cells:
        return
    start = next(iter(cells))
    seen = {start}
    stack = [start]
    while stack:
        r, c = stack.pop()
        for nr, nc in neighbors4(r, c, rows, cols):
            if (nr, nc) in cells and (nr, nc) not in seen:
                seen.add((nr, nc))
                stack.append((nr, nc))
    if seen != cells:
        raise SeatingError("损坏后考室不连通：剩余可坐格被损坏格割成互不四邻连通的区域")

def place_candidates(rows: int, cols: int, min_dist: int, candidates: list[dict],
                     damaged: frozenset[tuple[int, int]] | None = None
                     ) -> tuple[list[SeatAssign], list[dict]]:
    """贪心 row-major；损坏格禁止落人。

    未排原因分两类，且不与间距/同卷理由混淆：
    - 可坐格已坐满（容量被损坏格压缩）→ 容量不足，只写损坏禁坐格/可坐容量；
    - 仍有空可坐格但全部触发最小间距或同卷四邻约束 → 约束限制。
    """
    damaged = damaged or frozenset()
    # 连通才允许排：割裂时此处直接整场失败，杜绝在两块里强行分区坐人
    assert_connected(rows, cols, damaged)
    capacity = rows * cols - len(damaged)
    seats = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in damaged]
    occupied: dict[tuple[int, int], SeatAssign] = {}
    unplaced: list[dict] = []
    for cand in candidates:
        target: tuple[int, int] | None = None
        for r, c in seats:
            if (r, c) in occupied:
                continue
            ok = True
            for pos, other in occupied.items():
                if manhattan((r, c), pos) < min_dist:
                    ok = False
                    break
                if other.paper_id == cand["paper_id"] and (r, c) in neighbors4(pos[0], pos[1], rows, cols):
                    ok = False
                    break
            if not ok:
                continue
            for nr, nc in neighbors4(r, c, rows, cols):
                if (nr, nc) in occupied and occupied[(nr, nc)].paper_id == cand["paper_id"]:
                    ok = False
                    break
            if not ok:
                continue
            target = (r, c)
            break
        if target is None:
            entry = dict(cand)
            if len(occupied) >= capacity:
                entry["reason_kind"] = "capacity"
                entry["reason"] = (f"可坐座位不足：损坏禁坐格 {len(damaged)} 格，"
                                   f"可坐容量 {capacity} 人，该考生无法安排")
            else:
                entry["reason_kind"] = "constraint"
                entry["reason"] = "受最小曼哈顿间距与同卷四邻限制，无合适空位"
            unplaced.append(entry)
            continue
        r, c = target
        occupied[(r, c)] = SeatAssign(cand["id"], cand["name"], cand["ticket_no"], cand["paper_id"], r, c)
    return list(occupied.values()), unplaced

def find_violations(rows: int, cols: int, min_dist: int, assigns: list[SeatAssign]) -> list[Violation]:
    viols: list[Violation] = []
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            d = manhattan((a.row, a.col), (b.row, b.col))
            if d < min_dist:
                viols.append(Violation("distance", a.candidate_id, b.candidate_id,
                                       f"曼哈顿距离 {d} < 最小要求 {min_dist}"))
            if a.paper_id == b.paper_id and (b.row, b.col) in neighbors4(a.row, a.col, rows, cols):
                viols.append(Violation("same_paper_adjacent", a.candidate_id, b.candidate_id,
                                       f"同试卷套 {a.paper_id} 四邻相邻"))
    return viols

def plan_to_dict(assigns: list[SeatAssign], unplaced: list[dict], viols: list[Violation],
                 rows: int, cols: int, damaged: frozenset[tuple[int, int]] | None = None) -> dict:
    damaged = damaged or frozenset()
    capacity = rows * cols - len(damaged)
    return {
        "rows": rows,
        "cols": cols,
        "damaged": [{"row": r, "col": c} for r, c in sorted(damaged)],
        "assignments": [asdict(a) for a in assigns],
        "unplaced": unplaced,
        "violations": [asdict(v) for v in viols],
        "stats": {
            "seated": len(assigns),
            "unplaced": len(unplaced),
            "violations": len(viols),
            "capacity": capacity,
            "total_seats": rows * cols,
            "damaged": len(damaged),
        },
    }
