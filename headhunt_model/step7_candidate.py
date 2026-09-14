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

# Mirror of config/promotion_matrix.json ic_track — keep in sync.
# (grade, promotion_line_wan, bd_clients_required): line attached to the grade
# you get promoted INTO (6-month billing >= line). ACT is entry level (no line).
# Per 晋升机制 0414: max 3-level jump, management track exempt, billing (开票) basis.
PROMOTION_LINES = {
    "AC1": (18.0, 0), "AC2": (37.5, 0),
    "C1": (45.0, 0), "C2": (52.5, 0),
    "SC1": (60.0, 2), "SC2": (67.5, 3),
    "PC1": (75.0, 0), "PC2": (82.5, 0),
    "ECON": (90.0, 0),
}
PROMOTION_WINDOW_MONTHS = 6
PROMOTION_MAX_JUMP = 3

# business lines -> domain tag weights (sum per line = 100); used by line_match()
# and by apply_modifiers() for the domain bonus overlap check.
# Function-line taxonomy (bff_function_area_dict level-1). Identity weights:
# a line is matched by its own tag; BD line absorbs the commercial BD tag.
LINE_PROFILES = {
    "医学线": {"医学": 100},
    "临床运营线": {"临床运营": 100},
    "BD线": {"BD": 100, "商业BD": 100},
    "CMC线": {"CMC": 100},
    "注册线": {"注册": 100},
    "销售线": {"销售": 100},
    "市场线": {"市场": 100},
    "市场准入线": {"市场准入": 100},
    "综合线": {"综合/不限": 40, "医学": 15, "临床运营": 15, "BD": 10, "CMC": 10, "销售": 10},
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


# ---------- promotion (晋升机制 0414, billing basis) ----------

def promotion_view(current_grade: str, trailing_billing_wan=None, bd_clients: int = 0) -> dict:
    """Promotion perspective for an IC grade, per config/promotion_matrix.json.

    Rule: 6-month billing >= target grade's promotion line (and BD client count
    where required) -> promoted, max 3-level jump. Lines are cumulative, so the
    check stops at the first unmet grade. trailing_billing_wan=None returns path
    info only (external candidate / no billing data yet).
    """
    if current_grade not in GRADE_INDEX:
        return {"status": "UNKNOWN_GRADE", "current_grade": current_grade}
    idx = GRADE_INDEX[current_grade]
    nxt = []
    for step in range(1, PROMOTION_MAX_JUMP + 1):
        j = idx + step
        if j >= len(GRADE_TARGETS):
            break
        g, annual, quarterly = GRADE_TARGETS[j]
        line, bd = PROMOTION_LINES[g]
        nxt.append({"grade": g, "annual_wan": annual, "quarterly_wan": quarterly,
                    "promotion_line_wan": line, "bd_clients_required": bd})
    out = {"status": "OK", "current_grade": current_grade,
           "basis": "billing_wan", "window_months": PROMOTION_WINDOW_MONTHS,
           "max_level_jump": PROMOTION_MAX_JUMP, "next_grades": nxt,
           "progress": None}
    if trailing_billing_wan is None or not nxt:
        return out
    reached = current_grade
    for entry in nxt:
        ok_billing = trailing_billing_wan >= entry["promotion_line_wan"]
        ok_bd = bd_clients >= entry["bd_clients_required"]
        entry["met"] = ok_billing and ok_bd
        entry["billing_gap_wan"] = round(max(0.0, entry["promotion_line_wan"] - trailing_billing_wan), 2)
        entry["bd_gap"] = max(0, entry["bd_clients_required"] - bd_clients)
        if entry["met"]:
            reached = entry["grade"]
        else:
            break
    first = nxt[0]
    out["progress"] = {
        "trailing_billing_wan": trailing_billing_wan,
        "bd_clients": bd_clients,
        "next_grade": first["grade"],
        "next_line_wan": first["promotion_line_wan"],
        "progress_pct": round(100.0 * trailing_billing_wan / first["promotion_line_wan"], 1),
        "eligible_grade": reached,
        "promotion_ready": reached != current_grade,
    }
    return out


# ---------- salary / breakeven ----------

AFTER_TAX = 0.936            # after-tax coefficient on billing for commission base
COMMISSION_LADDER = ((40, 0.30), (60, 0.32), (100, 0.35), (150, 0.38), (200, 0.40), (float("inf"), 0.45))
INTERNAL_ANCHOR_BLEND = 0.6  # 60% internal, 40% market anchor
# Empirical ramp (hunter DB 2026-09-13, 67 billing-attributed advisors):
# Y1 ≈ 0.60 of mature level, Y2+ ≈ 1.0; median cost-cover quarter = Q3.
# Applied to the NPV cashflow, never to the discount rate (risk stays in
# cashflows, rate stays the uniform cost of capital).
RAMP_YEAR_FACTORS = (0.60, 1.0, 1.0)


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
    """Ramp-adjusted 3-year NPV feasibility check (wan). Year factors from
    RAMP_YEAR_FACTORS (empirical: Y1 0.6x mature, Y2+ 1.0x)."""
    npv = 0.0
    for y in range(1, years + 1):
        factor = RAMP_YEAR_FACTORS[y - 1] if y <= len(RAMP_YEAR_FACTORS) else 1.0
        profit = billing_wan * factor - _annual_cost_wan(monthly, billing_wan * factor, insurance_pct, overhead_wan)
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
    if not samples:  # no internal salary data at all (empty grade map)
        return {"p25": None, "p50": None, "p75": None,
                "source": "no_internal_data", "confidence": "LOW"}
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


# ---------- risk (CV 折减, hunter-calibrated 2026-09-14) ----------

CV_PRIOR = 1.08  # internal median quarterly-billing CV (hunter, n=36 advisors with >=6 quarters)
CV_CONC_A, CV_CONC_B = 0.65, 2.9  # OLS CV = 0.65 + 2.9x(max_deal/avg_annual); r=0.77, spearman 0.46
# evidence strengths: 2-point sample and concentration each weak (n=2 / proxy),
# internal prior anchors (Bayesian shrinkage, same philosophy as the three-layer model)
CV_SAMPLE_W, CV_CONC_W, CV_PRIOR_W = 2.0, 2.0, 4.0


def risk_profile(self_res: dict) -> dict:
    """Candidate CV estimate: two yearly points (sample) + deal concentration
    (calibrated OLS), shrunk toward the internal prior. Missing inputs degrade
    to prior-only (older template versions, minimal scored bundles)."""
    perf = self_res.get("dimensions", {}).get("performance", {})
    ans = perf.get("answers", {}) if isinstance(perf, dict) else {}
    claim = self_res.get("claimed_billing_wan") or 0.0
    y1, y2 = ans.get("perf_y1"), ans.get("perf_y2")
    max_deal = ans.get("perf_max_deal")

    cv_sample = None
    if isinstance(y1, (int, float)) and isinstance(y2, (int, float)) and (y1 + y2) > 0:
        cv_sample = round(abs(y1 - y2) * (2 ** 0.5) / (y1 + y2), 3)

    avg_annual = (y1 + y2) / 2.0 if cv_sample is not None else claim
    conc = None
    if isinstance(max_deal, (int, float)) and avg_annual > 0:
        conc = round(max_deal / avg_annual, 3)
    cv_conc = round(CV_CONC_A + CV_CONC_B * conc, 3) if conc is not None else None

    num, den = CV_PRIOR_W * CV_PRIOR, CV_PRIOR_W
    if cv_sample is not None:
        num += CV_SAMPLE_W * cv_sample
        den += CV_SAMPLE_W
    if cv_conc is not None:
        num += CV_CONC_W * cv_conc
        den += CV_CONC_W
    cv_used = round(num / den, 3)

    return {
        "cv_prior": CV_PRIOR,
        "cv_sample": cv_sample,
        "concentration": conc,
        "cv_from_concentration": cv_conc,
        "active_clients": ans.get("active_clients"),
        "top_client_share_pct": ans.get("top_client_share"),
        "cv_used": cv_used,
        "scenario_billing_factor": {
            "A_conservative": round(max(0.0, 1 - 0.5 * cv_used), 3),
            "B_base": 1.0,
            "C_optimistic": round(1 + 0.25 * cv_used, 3),
        },
    }


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
    # guard: self questionnaire must state the claimed billing (spec: no blank perf_amount)
    if self_res.get("claimed_billing_wan") is None:
        warnings.append("self questionnaire incomplete: claimed billing (perf_amount) not answered")
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
    promo = promotion_view(leveling["grade"])  # external candidate: path info only

    risk = risk_profile(self_res)
    eff = leveling["effective_billing_wan"] or 0.0
    risk["scenario_billing_wan"] = {
        k: round(eff * f, 2) for k, f in risk["scenario_billing_factor"].items()}

    band = salary_band(leveling["grade"], bundle.get("internal_samples", {}), bundle.get("anchors", {}))
    monthly = band["p50"]
    if monthly is None:
        risk["npv_scenarios"] = None
        warnings.append("no internal salary samples — fill config/candidate_grade_map.json "
                        "before salary band is meaningful")
        return {"status": "OK", "leveling": leveling, "band": band, "promotion": promo,
                "risk": risk,
                "breakeven_wan": None, "breakeven_monthly": None,
                "npv_quick_at_target": None, "line_match": lm, "divergence": div,
                "confidence": "LOW", "warnings": warnings}
    monthly = float(monthly)
    risk["npv_scenarios"] = {
        k: quick_npv(monthly, v) for k, v in risk["scenario_billing_wan"].items()}
    return {
        "status": "OK",
        "leveling": leveling,
        "band": band,
        "promotion": promo,
        "risk": risk,
        "breakeven_wan": breakeven_billing(monthly),
        "breakeven_monthly": monthly,
        "npv_quick_at_target": quick_npv(monthly, GRADE_TARGETS[GRADE_INDEX[leveling["grade"]]][1]),
        "line_match": lm,
        "divergence": div,
        "confidence": band["confidence"],
        "warnings": warnings,
    }


if __name__ == "__main__":
    # CLI smoke entry: python step7_candidate.py <bundle.json> [out.json]
    import json as _json, sys as _sys
    if len(_sys.argv) < 2:
        print("usage: python step7_candidate.py <bundle.json> [out.json]")
        _sys.exit(2)
    with open(_sys.argv[1], encoding="utf-8") as _f:
        _bundle = _json.load(_f)
    _out = assess(_bundle)
    _txt = _json.dumps(_out, ensure_ascii=False, indent=1)
    print(_txt)
    if len(_sys.argv) > 2:
        with open(_sys.argv[2], "w", encoding="utf-8") as _f:
            _f.write(_txt)
