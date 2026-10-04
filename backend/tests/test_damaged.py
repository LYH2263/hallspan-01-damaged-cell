import pytest

from app.services.seat_engine import (
    CapacityMismatchError,
    SeatAssign,
    is_connected,
    place_candidates,
    plan_to_dict,
    reconcile_plan,
)

CANDS = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1 + (i % 3)} for i in range(12)]


def test_corner_damage_stays_connected_capacity_29():
    # 种子场景：5x6 仅坏第 0 行第 0 列 → 仍连通可排，该格无人，容量 29
    damaged = {(0, 0)}
    assert is_connected(5, 6, damaged)
    assigns, unplaced = place_candidates(5, 6, 2, CANDS, damaged)
    assert not unplaced
    assert all((a.row, a.col) != (0, 0) for a in assigns)
    result = plan_to_dict(assigns, unplaced, [], 5, 6, damaged)
    assert result["stats"]["capacity"] == 29
    assert result["stats"]["capacity_total"] == 30
    assert result["stats"]["damaged"] == 1
    assert result["damaged"] == [{"row": 0, "col": 0}]
    reconcile_plan(result, 5, 6, damaged, len(CANDS))  # 不抛异常


def test_damage_isolating_corner_disconnects():
    # (0,1)、(1,0) 损坏 → (0,0) 被孤立成第二块
    assert not is_connected(5, 6, {(0, 1), (1, 0)})


def test_damage_around_corner_with_corner_damaged_disconnects():
    # (0,0) 已坏，再坏 (0,2)、(1,1) → (0,1) 被孤立
    assert not is_connected(5, 6, {(0, 0), (0, 2), (1, 1)})


def test_full_row_damage_disconnects():
    assert not is_connected(5, 6, {(2, c) for c in range(6)})


def test_empty_damage_full_grid_connected():
    assert is_connected(5, 6, set())
    assert is_connected(5, 6, None)
    assigns, unplaced = place_candidates(5, 6, 2, CANDS, set())
    result = plan_to_dict(assigns, unplaced, [], 5, 6, set())
    assert result["stats"]["capacity"] == 30
    assert result["stats"]["damaged"] == 0
    assert result["damaged"] == []


def test_damaged_cells_never_assigned():
    damaged = {(0, 0), (1, 1), (2, 2)}
    assigns, _ = place_candidates(5, 6, 2, CANDS, damaged)
    assert all((a.row, a.col) not in damaged for a in assigns)


def test_unplaced_reason_damage_capacity_not_spacing():
    # 损坏前 4 列共 20 格，剩 10 格仍连通；12 名考生坐不下 → 只能说明损坏容量不足
    damaged = {(r, c) for r in range(5) for c in range(4)}
    assert is_connected(5, 6, damaged)
    assigns, unplaced = place_candidates(5, 6, 2, CANDS, damaged)
    assert unplaced
    assert len(assigns) + len(unplaced) == len(CANDS)
    for u in unplaced:
        assert "间距" not in u["reason"]
        assert "同卷" not in u["reason"]
        assert "损坏" in u["reason"]


def test_unplaced_reason_spacing_when_capacity_sufficient():
    # 无损坏、容量够但间距约束坐不下 → 允许提间距/同卷
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": i} for i in range(3)]
    _, unplaced = place_candidates(3, 3, 3, cands, set())
    assert unplaced
    for u in unplaced:
        assert "损坏" not in u["reason"]


def test_reconcile_ok_for_consistent_plan():
    damaged = {(0, 0)}
    assigns, unplaced = place_candidates(5, 6, 2, CANDS, damaged)
    result = plan_to_dict(assigns, unplaced, [], 5, 6, damaged)
    reconcile_plan(result, 5, 6, damaged, len(CANDS))


def test_reconcile_rejects_wrong_capacity():
    damaged = {(0, 0)}
    result = plan_to_dict([], [], [], 5, 6, damaged)
    result["stats"]["capacity"] = 30  # 容量账被篡改
    with pytest.raises(CapacityMismatchError):
        reconcile_plan(result, 5, 6, damaged, 0)


def test_reconcile_rejects_person_on_damaged():
    assigns = [SeatAssign(1, "A", "T1", 1, 0, 0)]
    result = plan_to_dict(assigns, [], [], 5, 6, {(0, 0)})
    with pytest.raises(CapacityMismatchError):
        reconcile_plan(result, 5, 6, {(0, 0)}, 1)


def test_reconcile_rejects_map_list_mismatch():
    result = plan_to_dict([], [], [], 5, 6, {(0, 0)})
    result["damaged"] = []  # 图上空白损坏格与名单不符
    with pytest.raises(CapacityMismatchError):
        reconcile_plan(result, 5, 6, {(0, 0)}, 0)


def test_reconcile_rejects_headcount_mismatch():
    result = plan_to_dict([], [], [], 5, 6, set())
    with pytest.raises(CapacityMismatchError):
        reconcile_plan(result, 5, 6, set(), 3)  # 0 + 0 != 3
