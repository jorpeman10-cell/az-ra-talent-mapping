# -*- coding: utf-8 -*-
"""step7: external consultant candidate assessment engine (deterministic).
Leveling / salary band / line matching / divergence. No LLM, no network.

Consumes step6 score_questionnaire() outputs for both roles:
  self_res / hr_res: {"dimensions": {dim_id: {"score": float}}, "claimed_billing_wan",
                      "domain_tags": [str], "redline": bool}
"""
from step6_questionnaire import VERIFY_COEF

# Mirror of gateway policy_clauses.GRADE_TARGETS — keep in sync.
GRADE_TARGETS = (
    ("ACT", 30.0, 7.5), ("AC1", 40.0, 10.0), ("AC2", 50.0, 12.5),
    ("C1", 60.0, 15.0), ("C2", 70.0, 17.5), ("SC1", 80.0, 20.0),
    ("SC2", 90.0, 22.5), ("PC1", 100.0, 25.0), ("PC2", 110.0, 27.5),
    ("ECON", 120.0, 30.0),
)
GRADE_INDEX = {g[0]: i for i, g in enumerate(GRADE_TARGETS)}

# business lines -> domain tag weights (sum per line = 100); used by line_match()
# and by apply_modifiers() for the domain bonus overlap check.
LINE_PROFILES = {
    "肿瘤线": {"肿瘤": 70, "诊断/检验": 30},
    "糖尿病线": {"糖尿病/CVRM": 70, "综合/不限": 30},
    "中枢神经线": {"中枢神经": 70, "综合/不限": 30},
    "器械线": {"器械": 70, "综合/不限": 30},
    "综合线": {"综合/不限": 40, "肿瘤": 15, "糖尿病/CVRM": 15, "中枢神经": 15, "器械": 15},
}


def line_match(tags):
    """Rank business lines by tag overlap. Empty tags -> empty result."""
    if not tags:
        return {"lines": [], "top_line": None, "top_overlap_pct": 0.0}
    rows = []
    for line, profile in LINE_PROFILES.items():
        overlap = sum(w for t, w in profile.items() if t in tags)
        rows.append({"line": line, "overlap_pct": float(overlap)})
    rows.sort(key=lambda r: -r["overlap_pct"])
    return {"lines": rows, "top_line": rows[0]["line"], "top_overlap_pct": rows[0]["overlap_pct"]}


def resolve_base_grade(annual_wan: float) -> int:
    """Highest grade whose annual target <= annual_wan (floor ACT, cap ECON)."""
    idx = 0
    for i, (_g, annual, _q) in enumerate(GRADE_TARGETS):
        if annual_wan >= annual:
            idx = i
    return idx


def apply_modifiers(base_idx: int, self_res: dict, hr_res: dict):
    """Apply stability/speed downgrade and domain bonus. Returns (final_idx, rationale).

    Domain bonus needs HR domain score >=4 AND top-line overlap >=60% (computed
    from the candidate's domain tags). Half-level bonus rounds UP (int(x+0.5)),
    never Python's banker's rounding.
    """
    idx = float(base_idx)
    rationale = []
    hr = hr_res["dimensions"]
    if hr["stability"]["score"] < 3:
        idx -= 1
        rationale.append(f"stability HR score {hr['stability']['score']} < 3: -1 level")
    if hr["speed"]["score"] < 3:
        idx -= 1
        rationale.append(f"speed HR score {hr['speed']['score']} < 3: -1 level")
    overlap = line_match(self_res.get("domain_tags", []))["top_overlap_pct"]
    if hr["domain"]["score"] >= 4 and overlap >= 60:
        idx += 0.5
        rationale.append(f"domain depth >=4 with top-line overlap {overlap}%: +0.5 level")
    unclamped = int(idx + 0.5)  # half-up rounding
    final = min(len(GRADE_TARGETS) - 1, max(0, unclamped))
    if final != unclamped:
        rationale.append(f"clamped to grade index {final}")
    return final, rationale


def level_candidate(self_res: dict, hr_res: dict) -> dict:
    """Full leveling pass. Compliance redline vetoes before any grading."""
    if self_res.get("redline") or hr_res.get("redline"):
        return {"status": "REJECT_REVIEW", "grade": None, "base_grade": None,
                "effective_billing_wan": None, "verify_coefficient": None,
                "rationale": ["compliance redline triggered in questionnaire"],
                "warnings": []}
    claim = self_res.get("claimed_billing_wan") or 0.0
    coef = VERIFY_COEF[min(5, max(1, int(hr_res["dimensions"]["performance"]["score"])))]
    effective = round(claim * coef, 2)
    base_idx = resolve_base_grade(effective)
    final_idx, rationale = apply_modifiers(base_idx, self_res, hr_res)
    return {
        "status": "OK",
        "grade": GRADE_TARGETS[final_idx][0],
        "base_grade": GRADE_TARGETS[base_idx][0],
        "effective_billing_wan": effective,
        "verify_coefficient": coef,
        "rationale": rationale or ["no modifiers applied"],
        "warnings": [],
    }
