# tests/test_step7_assess.py
# Tests for line matching, divergence, full assess assembly, claim outlier guard.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from step7_candidate import line_match, divergence, assess

def base_bundle(claim=100, perf_hr=4, stab_hr=4, speed_hr=4, dom_hr=3, tags=None, **hr_over):
    # dom_hr defaults to 3: avoids the +0.5 domain bonus unless a test opts in
    tags = tags or ["肿瘤"]
    self_res = {"dimensions": {"performance": {"score": 5.0}, "domain": {"score": 5.0},
                 "speed": {"score": 4.0}, "stability": {"score": 4.0}, "compliance": {"score": 4.0}},
                "claimed_billing_wan": claim, "domain_tags": tags, "redline": False}
    hr_dims = {"performance": {"score": perf_hr}, "domain": {"score": dom_hr},
               "speed": {"score": speed_hr}, "stability": {"score": stab_hr},
               "compliance": {"score": 4.0}}
    hr_dims.update(hr_over)
    hr_res = {"dimensions": hr_dims, "claimed_billing_wan": None, "domain_tags": [], "redline": False}
    return {"self": self_res, "hr": hr_res,
            "internal_samples": {"C1": [15000, 17000], "SC1": [20000, 22000]},
            "anchors": {}}

def test_line_match_ranking():
    r = line_match(["肿瘤", "糖尿病/CVRM"])
    assert r["top_line"] == "肿瘤线"
    assert r["top_overlap_pct"] >= 60

def test_line_match_empty():
    r = line_match([])
    assert r["top_line"] is None
    assert r["lines"] == []

def test_divergence_flags():
    # NOTE: dom_hr=4 here (brief had the default 3, which made self domain 5.0 vs
    # hr 3 divergent and contradicted this test's own expectation). dom_hr=4 makes
    # the domain diff exactly 1.0, directly exercising the boundary below. The
    # divergence test does no leveling, so the +0.5 domain bonus is irrelevant here.
    b = base_bundle(dom_hr=4)
    r = divergence(b["self"], b["hr"])
    assert r["divergent"] == []                # self 5.0 vs hr 4.0 -> diff 1.0 is NOT > 1
    b2 = base_bundle(perf_hr=3, dom_hr=4)      # 5.0 vs 3.0 -> divergent
    r2 = divergence(b2["self"], b2["hr"])
    assert r2["divergent"] == ["performance"]
    assert r2["high_divergence"] is False      # only 1 dimension

def test_assess_happy_path():
    b = base_bundle(claim=90, perf_hr=4)       # 90*0.9=81 -> SC1
    out = assess(b)
    assert out["status"] == "OK"
    assert out["leveling"]["grade"] == "SC1"
    assert out["band"]["p50"] > 0
    assert out["breakeven_wan"] > 0
    assert "confidence" in out

def test_assess_reject_review():
    b = base_bundle(); b["hr"]["redline"] = True
    out = assess(b)
    assert out["status"] == "REJECT_REVIEW"

def test_assess_outlier_claim_rejected():
    b = base_bundle(claim=5000)                # 3-sigma style guard: >500 wan is absurd
    out = assess(b)
    assert out["status"] == "ERROR"
    assert any("claim" in w for w in out["warnings"])

def test_assess_blocks_incomplete_questionnaire():
    b = base_bundle()
    b["hr"]["dimensions"]["domain"]["score"] = 0; b["hr"]["dimensions"]["domain"]["missing"] = True
    out = assess(b)
    assert out["status"] == "ERROR"
    assert any("missing" in w for w in out["warnings"])

def test_assess_blocks_missing_claim():
    b = base_bundle()
    b["self"]["claimed_billing_wan"] = None
    out = assess(b)
    assert out["status"] == "ERROR"
    assert any("claimed billing" in w for w in out["warnings"])

def test_high_divergence_extra_discount():
    # 3 divergent dimensions WITHOUT triggering downgrades (hr scores exactly 3):
    # perf self5/hr3, domain self5/hr3, speed self5/hr3 -> high divergence,
    # no stability/speed downgrade (3 is not < 3), no domain bonus (3 is not >= 4)
    b = base_bundle(claim=100, perf_hr=3, dom_hr=3, speed_hr=3)
    b["self"]["dimensions"]["speed"]["score"] = 5.0  # self speed 5 vs hr 3 -> divergent
    out = assess(b)
    assert out["divergence"]["high_divergence"] is True
    # 100 * 0.8(perf3) * 0.9(divergence) = 72 -> C2
    assert out["leveling"]["grade"] == "C2"
    assert out["leveling"]["verify_coefficient"] == 0.8
    assert out["leveling"]["effective_billing_wan"] == 72.0

if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"): fn(); print(f"{name} PASS")
