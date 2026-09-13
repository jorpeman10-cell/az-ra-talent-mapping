# tests/test_candidate_promotion.py
# promotion_view(): 晋升机制 0414 rules — 6-month billing lines, BD client gate
# on SC1/SC2, max 3-level jump, path-only mode for external candidates.
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from candidate.engine import promotion_view, assess

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_matrix_config_in_sync():
    with open(os.path.join(BASE, "config", "promotion_matrix.json"), encoding="utf-8") as f:
        matrix = json.load(f)
    ic = {g["grade"]: g for g in matrix["ic_track"]}
    # every IC grade except ACT has a promotion line; SC1/SC2 carry BD gates
    assert ic["ACT"]["promotion_line_wan"] is None
    for g in ("AC1", "AC2", "C1", "C2", "SC1", "SC2", "PC1", "PC2", "ECON"):
        assert ic[g]["promotion_line_wan"] > 0, g
    assert ic["SC1"]["bd_clients_required"] == 2
    assert ic["SC2"]["bd_clients_required"] == 3
    assert matrix["rules"]["basis"] == "billing_wan"
    assert matrix["rules"]["window_months"] == 6
    assert matrix["rules"]["max_level_jump"] == 3


def test_path_only_for_external_candidate():
    out = promotion_view("AC1")
    assert out["status"] == "OK"
    assert out["progress"] is None
    assert [g["grade"] for g in out["next_grades"]] == ["AC2", "C1", "C2"]
    assert out["next_grades"][1]["promotion_line_wan"] == 45.0  # 0414: C1 线 45万


def test_progress_below_line():
    out = promotion_view("AC1", trailing_billing_wan=30.0)
    p = out["progress"]
    assert p["next_grade"] == "AC2"
    assert p["progress_pct"] == 80.0  # 30 / 37.5
    assert p["eligible_grade"] == "AC1"
    assert p["promotion_ready"] is False
    assert out["next_grades"][0]["billing_gap_wan"] == 7.5


def test_single_level_promotion():
    out = promotion_view("ACT", trailing_billing_wan=20.0)
    p = out["progress"]
    assert p["eligible_grade"] == "AC1"   # 20 >= 18 线
    assert p["promotion_ready"] is True
    # AC2 line 37.5 not met -> stops there
    assert out["next_grades"][0]["met"] is True
    assert out["next_grades"][1]["met"] is False


def test_multi_level_jump_capped_at_3():
    out = promotion_view("ACT", trailing_billing_wan=100.0)
    p = out["progress"]
    # 100 >= AC1(18)/AC2(37.5)/C1(45) lines; C2(52.5) not evaluated (max jump 3)
    assert p["eligible_grade"] == "C1"
    assert len(out["next_grades"]) == 3


def test_bd_gate_blocks_sc1():
    # C2 -> SC1 line 60万 met but only 1 BD client (< 2) -> blocked
    out = promotion_view("C2", trailing_billing_wan=65.0, bd_clients=1)
    p = out["progress"]
    assert p["eligible_grade"] == "C2"
    assert p["promotion_ready"] is False
    assert out["next_grades"][0]["bd_gap"] == 1
    # with 2 BD clients -> promoted
    out2 = promotion_view("C2", trailing_billing_wan=65.0, bd_clients=2)
    assert out2["progress"]["eligible_grade"] == "SC1"


def test_top_grade_has_no_next():
    out = promotion_view("ECON", trailing_billing_wan=200.0)
    assert out["next_grades"] == []
    assert out["progress"] is None


def test_unknown_grade():
    assert promotion_view("DIR5")["status"] == "UNKNOWN_GRADE"


def test_assess_includes_promotion_path():
    with open(os.path.join(BASE, "tests", "fixtures", "inputs",
                           "case1_high_claim_low_verify.json"), encoding="utf-8") as f:
        bundle = json.load(f)
    out = assess(bundle)
    assert out["status"] == "OK"
    promo = out["promotion"]
    assert promo["current_grade"] == out["leveling"]["grade"]
    assert promo["basis"] == "billing_wan"
    assert promo["progress"] is None  # external candidate: path info only


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
