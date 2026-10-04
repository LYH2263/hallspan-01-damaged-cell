import pytest
from app.services.seat_engine import (
    SeatingError, assert_connected, find_violations, manhattan, normalize_damaged,
    place_candidates, plan_to_dict, seatable_cells,
)

def test_manhattan():
    assert manhattan((0, 0), (2, 1)) == 3

def test_min_distance_placement():
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1 + (i % 2)} for i in range(4)]
    assigns, unplaced = place_candidates(4, 4, 2, cands)
    assert len(assigns) + len(unplaced) == 4
    for i, a in enumerate(assigns):
        for b in assigns[i+1:]:
            assert manhattan((a.row, a.col), (b.row, b.col)) >= 2

def test_same_paper_not_adjacent_in_result():
    cands = [
        {"id": 1, "name": "A", "ticket_no": "T1", "paper_id": 1},
        {"id": 2, "name": "B", "ticket_no": "T2", "paper_id": 1},
        {"id": 3, "name": "C", "ticket_no": "T3", "paper_id": 2},
    ]
    assigns, _ = place_candidates(3, 3, 1, cands)
    viols = find_violations(3, 3, 1, assigns)
    assert not any(v.kind == "same_paper_adjacent" for v in viols)

def test_violation_detection():
    from app.services.seat_engine import SeatAssign
    assigns = [
        SeatAssign(1, "A", "T1", 1, 0, 0),
        SeatAssign(2, "B", "T2", 1, 0, 1),
    ]
    viols = find_violations(2, 2, 2, assigns)
    kinds = {v.kind for v in viols}
    assert "distance" in kinds
    assert "same_paper_adjacent" in kinds

# ---------- 损坏禁坐格 ----------

def test_empty_damaged_is_full_grid_connected():
    dmg = normalize_damaged(5, 6, [])
    assert dmg == frozenset()
    assert assert_connected(5, 6, dmg) is None
    assert len(seatable_cells(5, 6, dmg)) == 30

def test_seed_damage_origin_still_connected_capacity_29():
    """种子仅坏第 0 行第 0 列：仍连通可排，该格无人，容量 29。"""
    dmg = normalize_damaged(5, 6, [{"row": 0, "col": 0}])
    assert_connected(5, 6, dmg)
    assert len(seatable_cells(5, 6, dmg)) == 29
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": i + 1} for i in range(29)]
    assigns, unplaced = place_candidates(5, 6, 1, cands, dmg)
    assert not unplaced
    assert all((a.row, a.col) != (0, 0) for a in assigns)
    result = plan_to_dict(assigns, unplaced, [], 5, 6, dmg)
    assert result["stats"]["capacity"] == 29
    assert result["stats"]["damaged"] == 1
    assert result["stats"]["seated"] == 29

def test_damaged_cell_never_occupied():
    dmg = normalize_damaged(4, 4, [{"row": 1, "col": 1}, {"row": 2, "col": 3}])
    assert_connected(4, 4, dmg)
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": i + 1} for i in range(14)]
    assigns, unplaced = place_candidates(4, 4, 1, cands, dmg)
    occupied = {(a.row, a.col) for a in assigns}
    assert occupied.isdisjoint(dmg)
    assert len(assigns) == 14 and not unplaced

def test_damage_cutting_room_fails_entire_run():
    """整列损坏把 5×6 割成左右两块：整场失败，不允许割裂分区排座。"""
    cut = [{"row": r, "col": 2} for r in range(5)]
    dmg = normalize_damaged(5, 6, cut)
    with pytest.raises(SeatingError) as ei:
        assert_connected(5, 6, dmg)
    msg = str(ei.value)
    assert "不连通" in msg
    # 失败说明只写损坏后不连通，不得与非法行列并句
    assert "越界" not in msg and "重复" not in msg

def test_damage_horizontal_cut_fails():
    cut = [{"row": 2, "col": c} for c in range(6)]
    dmg = normalize_damaged(5, 6, cut)
    with pytest.raises(SeatingError):
        assert_connected(5, 6, dmg)

def test_out_of_bounds_rejected_entirely():
    for bad in [{"row": -1, "col": 0}, {"row": 5, "col": 0}, {"row": 0, "col": 6}, {"row": 9, "col": 9}]:
        with pytest.raises(SeatingError) as ei:
            normalize_damaged(5, 6, [{"row": 0, "col": 0}, bad])
        assert "越界" in str(ei.value)

def test_duplicate_registration_rejected_entirely():
    with pytest.raises(SeatingError) as ei:
        normalize_damaged(5, 6, [{"row": 0, "col": 0}, {"row": 0, "col": 0}])
    assert "重复" in str(ei.value)

def test_capacity_unplaced_reason_not_spacing_wording():
    """因损坏格坐不下只进未排：说明不得写成间距不够或同卷相邻。"""
    dmg = normalize_damaged(3, 3, [{"row": 0, "col": 0}, {"row": 0, "col": 1}, {"row": 0, "col": 2}])
    assert_connected(3, 3, dmg)  # 剩两行仍连通
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": i + 1} for i in range(7)]
    assigns, unplaced = place_candidates(3, 3, 1, cands, dmg)
    assert len(assigns) == 6
    assert len(unplaced) == 1
    reason = unplaced[0]["reason"]
    assert unplaced[0]["reason_kind"] == "capacity"
    assert "间距" not in reason and "相邻" not in reason and "同卷" not in reason
    assert "29" not in reason  # 不得串账

def test_capacity_account_consistent():
    dmg = normalize_damaged(5, 6, [{"row": 0, "col": 0}, {"row": 4, "col": 5}])
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": i + 1} for i in range(40)]
    assigns, unplaced = place_candidates(5, 6, 1, cands, dmg)
    result = plan_to_dict(assigns, unplaced, [], 5, 6, dmg)
    st = result["stats"]
    assert st["capacity"] == 28
    assert st["total_seats"] == 30
    assert st["damaged"] == 2
    assert st["seated"] == 28 and st["unplaced"] == 12
    assert st["seated"] <= st["capacity"]
    assert all(u["reason_kind"] == "capacity" for u in unplaced)
