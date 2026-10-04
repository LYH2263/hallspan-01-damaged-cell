"""Exam seating: min Manhattan distance; same paper_id cannot be 4-neighbor adjacent.

Supports damaged (forbidden) cells: damaged cells never receive a candidate, and the
remaining sittable cells must stay 4-neighbor connected — the run gate lives in the
API layer, the geometry lives here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


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


class CapacityMismatchError(RuntimeError):
    """排座图、统计、未排名单的容量账对不齐 —— 整场失败。"""


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out


def sittable_cells(rows: int, cols: int, damaged: Iterable[tuple[int, int]] | None) -> set[tuple[int, int]]:
    blocked = set(damaged or ())
    return {(r, c) for r in range(rows) for c in range(cols)} - blocked


def is_connected(rows: int, cols: int, damaged: Iterable[tuple[int, int]] | None) -> bool:
    """True iff the sittable cells form a single 4-neighbor connected region.

    An empty sittable set is vacuously connected (zero regions, not two).
    """
    cells = sittable_cells(rows, cols, damaged)
    if not cells:
        return True
    blocked = set(damaged or ())
    start = next(iter(cells))
    seen = {start}
    stack = [start]
    while stack:
        r, c = stack.pop()
        for nr, nc in neighbors4(r, c, rows, cols):
            if (nr, nc) not in blocked and (nr, nc) not in seen:
                seen.add((nr, nc))
                stack.append((nr, nc))
    return seen == cells


def _unplaced_reason(candidates: list[dict], capacity: int, blocked: set[tuple[int, int]]) -> str:
    if len(candidates) > capacity:
        if blocked:
            # 损坏格挤压容量导致的未排 —— 不得写成间距不够或同卷相邻
            return "考室损坏导致可坐容量不足"
        return "考室可坐容量不足"
    return "最小间距或同卷相邻约束下无可坐位置"


def place_candidates(
    rows: int,
    cols: int,
    min_dist: int,
    candidates: list[dict],
    damaged: Iterable[tuple[int, int]] | None = None,
) -> tuple[list[SeatAssign], list[dict]]:
    """Greedy: try seats row-major; accept if manhattan >= min_dist to all placed AND no same paper 4-neigh.

    Damaged cells are skipped entirely — 损坏格禁止落人.
    """
    blocked = set(damaged or ())
    capacity = rows * cols - len(blocked)
    reason = _unplaced_reason(candidates, capacity, blocked)
    occupied: dict[tuple[int, int], SeatAssign] = {}
    unplaced: list[dict] = []
    for cand in candidates:
        placed = False
        for r in range(rows):
            for c in range(cols):
                if (r, c) in occupied or (r, c) in blocked:
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
                # also check 4-neigh same paper against current neighbors
                for nr, nc in neighbors4(r, c, rows, cols):
                    if (nr, nc) in occupied and occupied[(nr, nc)].paper_id == cand["paper_id"]:
                        ok = False
                        break
                if not ok:
                    continue
                assign = SeatAssign(cand["id"], cand["name"], cand["ticket_no"], cand["paper_id"], r, c)
                occupied[(r, c)] = assign
                placed = True
                break
            if placed:
                break
        if not placed:
            unplaced.append({**cand, "reason": reason})
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


def plan_to_dict(
    assigns: list[SeatAssign],
    unplaced: list[dict],
    viols: list[Violation],
    rows: int,
    cols: int,
    damaged: Iterable[tuple[int, int]] | None = None,
) -> dict:
    damaged_list = sorted(set(damaged or ()))
    capacity = rows * cols - len(damaged_list)
    return {
        "rows": rows,
        "cols": cols,
        "damaged": [{"row": r, "col": c} for r, c in damaged_list],
        "assignments": [asdict(a) for a in assigns],
        "unplaced": unplaced,
        "violations": [asdict(v) for v in viols],
        "stats": {
            "seated": len(assigns),
            "unplaced": len(unplaced),
            "violations": len(viols),
            "capacity": capacity,
            "capacity_total": rows * cols,
            "damaged": len(damaged_list),
        },
    }


def reconcile_plan(
    result: dict,
    rows: int,
    cols: int,
    damaged: Iterable[tuple[int, int]] | None,
    total_candidates: int,
) -> None:
    """排座图空白损坏格、统计可坐容量、未排名单必须对同一套容量账；对不齐整场失败。"""
    blocked = set(damaged or ())
    problems: list[str] = []
    stats = result.get("stats", {})
    on_map = {(d["row"], d["col"]) for d in result.get("damaged", [])}
    if on_map != blocked:
        problems.append("排座图损坏格与已保存名单不一致")
    if stats.get("capacity") != rows * cols - len(blocked):
        problems.append("统计可坐容量与损坏名单不符")
    if stats.get("damaged") != len(blocked):
        problems.append("统计损坏格数与名单不符")
    if any((a["row"], a["col"]) in blocked for a in result.get("assignments", [])):
        problems.append("损坏格上存在已排座位")
    if stats.get("seated") != len(result.get("assignments", [])):
        problems.append("统计已排人数与排座图不符")
    if stats.get("unplaced") != len(result.get("unplaced", [])):
        problems.append("统计未排人数与未排名单不符")
    if stats.get("seated", 0) + stats.get("unplaced", 0) != total_candidates:
        problems.append("已排加未排不等于考生总数")
    if stats.get("seated", 0) > stats.get("capacity", 0):
        problems.append("已排人数超过可坐容量")
    if problems:
        raise CapacityMismatchError("；".join(problems))
