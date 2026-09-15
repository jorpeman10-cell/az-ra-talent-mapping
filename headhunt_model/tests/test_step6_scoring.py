# Tests for questionnaire scoring: dimension scores, claims, tags, redline, verify coefficient.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
from step6_questionnaire import default_template, score_questionnaire, verify_coefficient

T = default_template()

SELF_FULL = {
    "perf_amount": 80, "perf_max_deal": 25, "perf_desc": "某CDMO管线总监单",
    "dom_tags": ["医学", "临床运营"], "dom_share": "医学70% 临床运营30%",
    "speed_jc": "1-2天", "speed_case": "接到JC当天出mapping",
    "stab_moves": "1次", "stab_reason": "平台倒闭",
    "comp_share": "按规则分单",
}
HR_FULL = {
    "perf_verify": "有部分佐证，数字合理", "perf_probe": "基本自洽，个别含糊",
    "dom_depth": "领域知识扎实",
    "speed_probe": "路径可行",
    "stab_verify": "基本可信",
    "comp_redline": "拒绝，边界感一般",
}

def test_self_scores_and_claim():
    r = score_questionnaire(T, SELF_FULL, "self")
    assert r["claimed_billing_wan"] == 80
    assert r["domain_tags"] == ["医学", "临床运营"]
    assert r["redline"] is False
    assert r["dimensions"]["speed"]["score"] == 4
    assert abs(r["dimensions"]["performance"]["score"] - 5.0) < 1e-9  # no choice in self perf -> neutral 5.0? see rule below

def test_hr_scores():
    r = score_questionnaire(T, HR_FULL, "hr")
    assert r["dimensions"]["performance"]["score"] == 4.0
    assert r["dimensions"]["compliance"]["score"] == 4.0
    assert r["redline"] is False

def test_redline_detection():
    hr = dict(HR_FULL, comp_redline="承认做过类似行为")
    r = score_questionnaire(T, hr, "hr")
    assert r["redline"] is True

def test_missing_choice_answer_scores_zero_and_flags():
    hr = dict(HR_FULL); hr.pop("dom_depth")
    r = score_questionnaire(T, hr, "hr")
    assert r["dimensions"]["domain"]["score"] == 0
    assert r["dimensions"]["domain"]["missing"] is True

def test_verify_coefficient_mapping():
    hr = score_questionnaire(T, HR_FULL, "hr")  # perf score 4.0
    assert verify_coefficient(hr) == 0.9
    hr2 = score_questionnaire(T, dict(HR_FULL, perf_verify="明显夸大或自相矛盾"), "hr")  # (1+4)/2=2.5 -> 0.65? see rule
    assert verify_coefficient(hr2) == 0.65  # 2.5 rounds to nearest step boundary: floor(2.5)=2 -> 0.65

def test_template_version_recorded():
    r = score_questionnaire(T, SELF_FULL, "self")
    assert r["template_version"] == T["version"]

if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_"): fn(); print(f"{name} PASS")


def test_coef_only_question_skipped_in_scores_and_optional():
    # 2026-09-16 perf_market_env: coef_only questions must not enter the
    # dimension score (verify coefficient stays pure) and may be unanswered
    # (old archives) without setting missing.
    from step6_questionnaire import score_questionnaire
    t = default_template()
    t["version"] = 3
    perf = next(d for d in t["dimensions"] if d["id"] == "performance")
    perf["hr_questions"].append({
        "id": "perf_market_env", "type": "choice", "coef_only": True,
        "label": "该业绩取得时的市场环境",
        "options": [
            {"label": "冷门赛道或小平台资源做成", "coef": 1.10},
            {"label": "正常市场环境", "coef": 1.00},
            {"label": "热门赛道且大平台资源依赖高", "coef": 0.85},
        ]})
    base_answers = {"perf_verify": "有部分佐证，数字合理",
                    "perf_probe": "基本自洽，个别含糊"}
    answered = score_questionnaire(t, {**base_answers,
                                       "perf_market_env": "热门赛道且大平台资源依赖高"}, "hr")
    unanswered = score_questionnaire(t, base_answers, "hr")
    perf_a = answered["dimensions"]["performance"]; perf_u = unanswered["dimensions"]["performance"]
    assert not perf_a.get("missing") and not perf_u.get("missing")
    assert answered["dimensions"]["performance"]["score"] == \
           unanswered["dimensions"]["performance"]["score"]
    assert answered["dimensions"]["performance"]["answers"]["perf_market_env"] == \
           "热门赛道且大平台资源依赖高"
