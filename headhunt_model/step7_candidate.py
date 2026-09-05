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


# ---------- salary / breakeven ----------

AFTER_TAX = 0.936            # after-tax coefficient on billing for commission base
COMMISSION_LADDER = ((40, 0.30), (60, 0.32), (100, 0.35), (150, 0.38), (200, 0.40), (float("inf"), 0.45))
INTERNAL_ANCHOR_BLEND = 0.6  # 60% internal, 40% market anchor


def tier(billing_wan: float) -> float:
    for cap, rate in COMMISSION_LADDER:
        if billing_wan <= cap:
            return rate
    return 0.45


def _annual_cost_wan(monthly: float, billing_wan: float, insurance_pct: float, overhead_wan: float) -> float:
    """Total company cost: cash comp = max(base, after-tax billing x tier) + social + overhead."""
    base_wan = monthly * 12 / 10000.0
    cash = max(base_wan, AFTER_TAX * billing_wan * tier(billing_wan))
    social = base_wan * insurance_pct / 100.0
    return cash + social + overhead_wan


def breakeven_billing(monthly: float, insurance_pct: float = 28.0, overhead_wan: float = 6.37) -> float:
    """Smallest annual billing (wan, step 1) where profit >= 0."""
    B = 1.0
    while B < 10000.0:
        if B - _annual_cost_wan(monthly, B, insurance_pct, overhead_wan) >= 0:
            return round(B, 2)
        B += 1.0
    return float("inf")


def quick_npv(monthly: float, billing_wan: float, years: int = 3, discount: float = 0.12,
              insurance_pct: float = 28.0, overhead_wan: float = 6.37) -> float:
    """Flat-billing 3-year NPV feasibility check (wan)."""
    npv = 0.0
    for y in range(1, years + 1):
        profit = billing_wan - _annual_cost_wan(monthly, billing_wan, insurance_pct, overhead_wan)
        npv += profit / ((1 + discount) ** y)
    return round(npv, 2)


def _pct(values):
    """P25/P50/P75 of monthly salaries. P50 uses the true median so a
    two-sample grade (e.g. [20000, 22000]) yields 21000, not 20000."""
    s = sorted(values)
    n = len(s)
    p25 = s[min(n - 1, int(0.25 * (n - 1)))]
    p50 = (s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2.0)
    p75 = s[min(n - 1, int(0.75 * (n - 1)))]
    return p25, p50, p75


def salary_band(grade: str, internal_samples: dict, anchors: dict) -> dict:
    """Salary band for a grade. Blend internal percentiles with market anchors 6:4.

    - internal samples pooled from grade +/-1 when the exact grade is empty
    - no anchor -> internal only, confidence LOW (external candidates cap at MEDIUM)
    """
    samples = list(internal_samples.get(grade, []))
    source = "internal" if samples else "interpolated"
    if not samples:
        for g, idx in GRADE_INDEX.items():
            if abs(idx - GRADE_INDEX[grade]) == 1:
                samples.extend(internal_samples.get(g, []))
    if not samples:  # last resort: whole pool
        for v in internal_samples.values():
            samples.extend(v)
    p25, p50, p75 = _pct(samples)
    conf = "MEDIUM" if len(internal_samples.get(grade, [])) >= 2 else "LOW"
    anchor = anchors.get(grade)
    if anchor:
        p25 = round(INTERNAL_ANCHOR_BLEND * p25 + (1 - INTERNAL_ANCHOR_BLEND) * anchor["p25"])
        p50 = round(INTERNAL_ANCHOR_BLEND * p50 + (1 - INTERNAL_ANCHOR_BLEND) * anchor["p50"])
        p75 = round(INTERNAL_ANCHOR_BLEND * p75 + (1 - INTERNAL_ANCHOR_BLEND) * anchor["p75"])
        source = "blend"
        conf = "MEDIUM"
    return {"p25": p25, "p50": p50, "p75": p75, "source": source, "confidence": conf}


def load_internal_samples(salary_map: dict, grade_map: dict) -> dict:
    """salary_loader {name: {'base_monthly':..}} x {name: grade} -> {grade: [monthly,..]}."""
    out = {}
    for name, grade in grade_map.items():
        if name in salary_map:
            out.setdefault(grade, []).append(salary_map[name]["base_monthly"])
    return out


# ---------- line matching & divergence ----------
# NOTE: LINE_PROFILES and line_match() are defined in the leveling section above
# (apply_modifiers needs them); this section adds divergence and assess().

CLAIM_ABSURD_WAN = 500.0  # claims above this are treated as data errors (3-sigma style guard)


def divergence(self_res, hr_res):
    divergent = []
    for dim, entry in self_res["dimensions"].items():
        if dim not in hr_res["dimensions"]:
            continue
        if abs(entry["score"] - hr_res["dimensions"][dim]["score"]) > 1.0:
            divergent.append(dim)
    return {"divergent": divergent, "high_divergence": len(divergent) >= 3}


# ---------- full assessment ----------

def assess(bundle: dict) -> dict:
    """bundle = {"self", "hr", "internal_samples", "anchors"}. Deterministic end-to-end."""
    self_res, hr_res = bundle["self"], bundle["hr"]
    warnings = []

    # guard: incomplete questionnaire
    for role, res in (("self", self_res), ("hr", hr_res)):
        for dim, entry in res["dimensions"].items():
            if entry.get("missing"):
                warnings.append(f"{role} questionnaire incomplete: dimension '{dim}' has missing answers")
    # guard: absurd claim
    if (self_res.get("claimed_billing_wan") or 0) > CLAIM_ABSURD_WAN:
        warnings.append(f"claimed billing {self_res.get('claimed_billing_wan')} wan exceeds "
                        f"{CLAIM_ABSURD_WAN} wan guard — HR must verify the number")
    if warnings:
        return {"status": "ERROR", "warnings": warnings}

    lm = line_match(self_res.get("domain_tags", []))

    div = divergence(self_res, hr_res)
    if div["high_divergence"]:
        self_res = dict(self_res, claimed_billing_wan=(self_res.get("claimed_billing_wan") or 0) * 0.9)

    leveling = level_candidate(self_res, hr_res)
    if leveling["status"] != "OK":
        return {"status": leveling["status"], "leveling": leveling, "line_match": lm,
                "divergence": div, "warnings": warnings}

    band = salary_band(leveling["grade"], bundle.get("internal_samples", {}), bundle.get("anchors", {}))
    monthly = float(band["p50"])
    return {
        "status": "OK",
        "leveling": leveling,
        "band": band,
        "breakeven_wan": breakeven_billing(monthly),
        "breakeven_monthly": monthly,
        "npv_quick_at_target": quick_npv(monthly, GRADE_TARGETS[GRADE_INDEX[leveling["grade"]]][1]),
        "line_match": lm,
        "divergence": div,
        "confidence": band["confidence"],
        "warnings": warnings,
    }
