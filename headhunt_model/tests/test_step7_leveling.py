# tests/test_step7_leveling.py
# Tests for candidate leveling: effective billing, base grade mapping, modifiers, veto.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from step7_candidate import resolve_base_grade, apply_modifiers, level_candidate, GRADE_INDEX

def mk(claim, perf_hr, stab_hr=4, speed_hr=4, dom_hr=3, speed_self=4, stab_self=4):
    # dom_hr defaults to 3: avoids the +0.5 domain bonus unless a test opts in
    """Build minimal self/hr questionnaire results (dimension scores only)."""
    self_res = {"dimensions": {"performance": {"score": 5.0}, "domain": {"score": 5.0},
                 "speed": {"score": speed_self}, "stability": {"score": stab_self},
                 "compliance": {"score": 4.0}},
                "claimed_billing_wan": claim, "domain_tags": ["医学"], "redline": False}
    hr_res = {"dimensions": {"performance": {"score": perf_hr}, "domain": {"score": dom_hr},
               "speed": {"score": speed_hr}, "stability": {"score": stab_hr},
               "compliance": {"score": 4.0}},
              "claimed_billing_wan": None, "domain_tags": [], "redline": False}
    return self_res, hr_res

def test_base_grade_mapping():
    assert resolve_base_grade(0) == 0          # below ACT
    assert resolve_base_grade(30) == 0         # exactly ACT
    assert resolve_base_grade(55) == 2         # AC2 (50)
    assert resolve_base_grade(60) == 3         # C1
    assert resolve_base_grade(500) == 9        # capped at ECON
    assert resolve_base_grade(5000) == 9       # outlier NOT special-cased here (3σ guard is in assess)

def test_effective_billing_applies_verify_coef():
    s, h = mk(claim=100, perf_hr=4)            # coef 0.9 -> 90 -> SC2
    out = level_candidate(s, h)
    assert out["status"] == "OK"
    assert out["grade"] == "SC2"
    assert out["effective_billing_wan"] == 90.0

def test_stability_modifier_downgrades():
    s, h = mk(claim=60, perf_hr=5, stab_hr=2)  # coef 1.0 -> 60 = C1, stability<3 -> -1 -> AC2
    out = level_candidate(s, h)
    assert out["grade"] == "AC2"
    assert any("stability" in r for r in out["rationale"])

def test_speed_modifier_stacks():
    s, h = mk(claim=60, perf_hr=5, stab_hr=2, speed_hr=2)  # C1(idx3) -1(stab) -1(speed) -> idx1 AC1
    out = level_candidate(s, h)
    assert out["grade"] == "AC1"

def test_domain_bonus_half_level():
    # domain>=4 and top line overlap>=60%: +0.5 level rounds up
    s, h = mk(claim=50, perf_hr=5, dom_hr=5)   # AC2 (idx2) +0.5 -> 2.5 -> rounds to 3 (C1)
    s["domain_tags"] = ["医学", "临床运营"]
    out = level_candidate(s, h)
    assert out["grade"] == "C1"

def test_redline_veto():
    s, h = mk(claim=100, perf_hr=5)
    h["redline"] = True
    out = level_candidate(s, h)
    assert out["status"] == "REJECT_REVIEW"
    assert "grade" not in out or out.get("grade") is None

def test_floor_ceiling_not_exceeded():
    s, h = mk(claim=120, perf_hr=1, stab_hr=1, speed_hr=1)  # ECON -1 -1 = PC1... coef0.5->60=C1 first
    out = level_candidate(s, h)  # coef 0.5 -> 60 -> C1(idx3) -1(stab) -1(speed) -> idx1 AC1
    assert out["grade"] == "AC1"
    s2, h2 = mk(claim=20, perf_hr=5, stab_hr=1, speed_hr=1)  # 20 < ACT -> idx0, -2 -> floor ACT
    out2 = level_candidate(s2, h2)
    assert out2["grade"] == "ACT"

if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"): fn(); print(f"{name} PASS")
