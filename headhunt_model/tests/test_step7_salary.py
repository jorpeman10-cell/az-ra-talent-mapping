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
        # 2026-09-16 model: VAT-exclusive net revenue, 34% social
        from step7_candidate import net_billing, commission_cash
        cash = max(monthly * 12 / 10000, commission_cash(B))
        social = monthly * 12 / 10000 * 0.34
        return net_billing(B) - cash - social - 6.37
    assert profit(b, 15000) >= 0
    assert profit(b - 1, 15000) < 0

SAMPLES = {"C1": [15000, 16000, 17000], "C2": [18000], "SC1": [20000, 22000]}

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


# ---------- 2026-09-16 model revision (Steven ruling) ----------
# VAT 6% (price-tax separation: net = X/1.06), employer social 34%,
# overhead 6.37 wan. Two lines: breakeven (company cash-neutral) and
# profit-achievement (commission fully covers salary: (X/1.06)*tier = salary*12).
from step7_candidate import (
    VAT_RATE, INSURANCE_PCT, OVERHEAD_WAN, net_billing, commission_cash,
    profit_achievement_billing, _annual_cost_wan,
)

def test_model_constants_steven_ruling():
    assert VAT_RATE == 0.06
    assert INSURANCE_PCT == 34.0
    assert OVERHEAD_WAN == 6.37

def test_net_billing_is_vat_exclusive():
    assert abs(net_billing(106.0) - 100.0) < 1e-9
    assert abs(commission_cash(106.0) - 100.0 * 0.38) < 1e-9  # tier(106)=0.38 (>100)

def test_breakeven_accounts_for_vat_and_social34():
    # monthly 15060 -> salary annual 18.072 wan. While commission < salary:
    # net = 1.34*18.072 + 6.37 = 30.626 -> B = 30.626*1.06 = 32.46
    be = breakeven_billing(15060.0)
    assert 31.5 < be < 33.5, be
    net = net_billing(be)
    cost_floor = 15060 * 12 / 10000 * (1 + INSURANCE_PCT / 100) + OVERHEAD_WAN
    assert net >= cost_floor - 0.01          # net revenue covers full cost
    assert net_billing(be - 1.0) < cost_floor - 0.01  # one step below fails

def test_profit_achievement_line_commission_covers_salary():
    # (X/1.06)*tier(X) = 18.072 wan. tier 0.32 window -> X ~ 59.9
    line = profit_achievement_billing(15060.0)
    assert 58.0 < line < 62.0, line
    earned = commission_cash(line)
    assert abs(earned - 15060 * 12 / 10000) < 0.05

def test_band_anchor_driven_when_internal_sample_lt3():
    # Single internal sample must not masquerade as a percentile
    # distribution (2026-09-15 romona: 1 sample -> 15060/15060/15460).
    anchors = {"PC1": {"p25": 10000, "p50": 14000, "p75": 15000}}
    band = salary_band("PC1", {"PC1": [15100.0]}, anchors)
    assert band["source"] == "anchor"
    assert (band["p25"], band["p50"], band["p75"]) == (10000, 14000, 15000)

def test_band_blends_when_3plus_internal_samples():
    anchors = {"C1": {"p25": 10000, "p50": 12000, "p75": 14000}}
    samples = {"C1": [15000.0, 16000.0, 17000.0]}
    band = salary_band("C1", samples, anchors)
    assert band["source"] == "blend"
    # 0.6*internal + 0.4*anchor on every percentile
    assert band["p50"] == round(0.6 * 16000 + 0.4 * 12000)


# ---------- 2026-09-16 market-difficulty + platform-transition (Steven) ----------
from step7_candidate import MARKET_ENV_COEF, PLATFORM_TRANSITION_FACTOR, level_candidate

def test_market_env_constants():
    assert MARKET_ENV_COEF["冷门赛道或小平台资源做成"] == 1.10
    assert MARKET_ENV_COEF["正常市场环境"] == 1.00
    assert MARKET_ENV_COEF["热门赛道且大平台资源依赖高"] == 0.85
    assert 0.5 < PLATFORM_TRANSITION_FACTOR < 0.9

def test_leveling_applies_market_and_transition():
    self_res = {"claimed_billing_wan": 100.0, "domain_tags": ["医学"],
                "domain_share": "医学100%", "redline": False}
    dims = {d: {"score": 4, "answers": {}} for d in
            ("performance", "domain", "speed", "stability", "compliance")}
    dims["performance"]["answers"]["perf_market_env"] = "热门赛道且大平台资源依赖高"
    hr_res = {"redline": False, "dimensions": dims}
    out = level_candidate(self_res, hr_res)
    assert out["verify_coefficient"] == 0.9
    assert out["effective_billing_wan"] == 90.0
    assert out["market_coef"] == 0.85
    # expected first-year = 90 x 0.85 x 0.70 = 53.55
    assert out["expected_first_year_wan"] == 53.55

def test_leveling_market_env_defaults_neutral_when_unanswered():
    # Old questionnaires (pre-template-v3) have no perf_market_env answer —
    # neutral 1.0, still expected-first-year applies the transition factor.
    self_res = {"claimed_billing_wan": 100.0, "domain_tags": ["医学"],
                "domain_share": "医学100%", "redline": False}
    dims = {d: {"score": 4, "answers": {}} for d in
            ("performance", "domain", "speed", "stability", "compliance")}
    hr_res = {"redline": False, "dimensions": dims}
    out = level_candidate(self_res, hr_res)
    assert out["market_coef"] == 1.0
    assert out["expected_first_year_wan"] == 63.0  # 90 x 1.0 x 0.7

def test_quick_npv_first_year_override():
    # Y1 uses the explicit first-year billing (market+transition adjusted);
    # Y2+ use the mature billing.
    npv = quick_npv(14000.0, 90.0, first_year_wan=53.55)
    manual = 0.0
    for y, billing in ((1, 53.55), (2, 90.0), (3, 90.0)):
        profit = net_billing(billing) - _annual_cost_wan(14000.0, billing)
        manual += profit / (1.12 ** y)
    assert abs(npv - round(manual, 2)) < 0.05
