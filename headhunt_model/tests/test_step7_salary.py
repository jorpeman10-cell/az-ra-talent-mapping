# tests/test_step7_salary.py
# Tests for salary band, commission tier, breakeven, quick NPV.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from step7_candidate import tier, breakeven_billing, quick_npv, salary_band, load_internal_samples

def test_tier_ladder():
    assert tier(30) == 0.30
    assert tier(40) == 0.30
    assert tier(41) == 0.32
    assert tier(100) == 0.35
    assert tier(250) == 0.45

def test_breakeven_monotonic_and_positive():
    # At breakeven billing, profit ~ 0 (within one step of 1 wan)
    b = breakeven_billing(15000)  # 1.8 wan/month
    assert b > 0
    # verify: profit at b >= 0, profit at b-1 < 0
    def profit(B, monthly):
        cash = max(monthly * 12 / 10000, 0.936 * B * tier(B))
        social = monthly * 12 / 10000 * 0.28
        return B - cash - social - 6.37
    assert profit(b, 15000) >= 0
    assert profit(b - 1, 15000) < 0

SAMPLES = {"C1": [15000, 17000], "C2": [18000], "SC1": [20000, 22000]}

def test_band_blends_internal_and_anchor():
    anchors = {"C1": {"p25": 14000, "p50": 16000, "p75": 18000}}
    band = salary_band("C1", SAMPLES, anchors)
    assert band["source"] == "blend"
    assert band["confidence"] == "MEDIUM"
    # 6:4 blend of internal p50 (16000) and anchor p50 (16000) = 16000
    assert band["p50"] == 16000

def test_band_internal_only_when_no_anchor():
    band = salary_band("C2", SAMPLES, {})
    assert band["source"] == "internal"
    assert band["confidence"] == "LOW"   # single-sample grade, no anchor
    assert band["p50"] == 18000

def test_band_interpolates_from_neighbor_grades():
    band = salary_band("SC2", SAMPLES, {})   # no SC2 samples; neighbors SC1 have 2
    assert band["source"] == "interpolated"
    assert band["p50"] == 21000              # mean of SC1 samples
    assert band["confidence"] == "LOW"

def test_band_no_internal_data():
    band = salary_band("C1", {}, {})
    assert band["source"] == "no_internal_data"
    assert band["p50"] is None and band["confidence"] == "LOW"

def test_load_internal_samples():
    salary_map = {"张三": {"base_monthly": 15000}, "李四": {"base_monthly": 20000}}
    grade_map = {"张三": "C1", "李四": "SC1"}
    out = load_internal_samples(salary_map, grade_map)
    assert out == {"C1": [15000], "SC1": [20000]}

def test_quick_npv_positive_when_profitable():
    # 15k/month against 100 wan/year billing: strong margin -> positive NPV
    assert quick_npv(15000, 100) > 0

if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"): fn(); print(f"{name} PASS")
