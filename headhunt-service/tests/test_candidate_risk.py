# tests/test_candidate_risk.py
# risk_profile(): CV estimate — two yearly points + deal concentration shrunk
# toward the internal prior; graceful degradation on legacy/minimal bundles.
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from candidate.engine import risk_profile, CV_PRIOR, assess
from candidate.questionnaire import _DEFAULT, score_questionnaire, validate_template

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _self(answers=None, claim=90.0):
    return {"dimensions": {"performance": {"score": 5.0, "answers": answers or {}}},
            "claimed_billing_wan": claim, "domain_tags": ["医学"], "redline": False}


def test_template_v2_has_cv_questions_and_validates():
    assert _DEFAULT["version"] == 3
    ids = [q["id"] for d in _DEFAULT["dimensions"] for q in d["self_questions"]]
    for qid in ("perf_y1", "perf_y2", "active_clients", "top_client_share"):
        assert qid in ids, qid
    assert validate_template(_DEFAULT) == []


def test_v2_scoring_captures_new_numbers():
    res = score_questionnaire(_DEFAULT, {
        "perf_amount": 90, "perf_y1": 100, "perf_y2": 80, "perf_max_deal": 25,
        "active_clients": 6, "top_client_share": 40, "perf_desc": "x",
        "dom_tags": ["医学"], "dom_share": "医学100%", "speed_jc": "1-2天",
        "speed_case": "x", "stab_moves": "1次", "stab_reason": "x",
        "comp_share": "按规则分单"}, "self")
    ans = res["dimensions"]["performance"]["answers"]
    assert ans["perf_y1"] == 100 and ans["perf_y2"] == 80
    assert ans["active_clients"] == 6 and ans["top_client_share"] == 40
    assert res["template_version"] == 3
    # number questions never mark the dimension missing
    assert "missing" not in res["dimensions"]["performance"]


def test_prior_only_when_no_inputs():
    r = risk_profile(_self())
    assert r["cv_sample"] is None
    assert r["concentration"] is None
    assert r["cv_used"] == CV_PRIOR  # 1.08


def test_cv_sample_from_two_yearly_points():
    r = risk_profile(_self({"perf_y1": 120, "perf_y2": 60}))
    # |120-60|*sqrt(2)/(180) = 0.471
    assert r["cv_sample"] == 0.471
    # shrunk toward prior 1.08 with weights 2:4 -> (2*0.471+4*1.08)/6
    assert r["cv_used"] == round((2 * 0.471 + 4 * CV_PRIOR) / 6, 3)


def test_concentration_feeds_ols():
    r = risk_profile(_self({"perf_max_deal": 45}, claim=90))
    assert r["concentration"] == 0.5
    assert r["cv_from_concentration"] == round(0.65 + 2.9 * 0.5, 3)  # 2.1
    assert r["cv_used"] == round((2 * 2.1 + 4 * CV_PRIOR) / 6, 3)


def test_scenario_factors_monotonic():
    r = risk_profile(_self())
    f = r["scenario_billing_factor"]
    assert f["A_conservative"] < f["B_base"] < f["C_optimistic"]
    assert f["A_conservative"] >= 0.0


def test_assess_carries_risk_block():
    with open(os.path.join(BASE, "tests", "fixtures", "inputs",
                           "case1_high_claim_low_verify.json"), encoding="utf-8") as f:
        bundle = json.load(f)
    out = assess(bundle)
    assert out["status"] == "OK"
    risk = out["risk"]
    assert risk["cv_prior"] == CV_PRIOR
    # minimal fixture bundle has no answers -> prior-only
    assert risk["cv_used"] == CV_PRIOR
    eff = out["leveling"]["effective_billing_wan"]
    assert risk["scenario_billing_wan"]["B_base"] == eff
    npvs = risk["npv_scenarios"]
    assert npvs["A_conservative"] < npvs["B_base"] < npvs["C_optimistic"]


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
