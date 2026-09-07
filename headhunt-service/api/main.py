# -*- coding: utf-8 -*-
"""FastAPI 服务: 看板 / 单人详情 / 调薪扫描 / 配置管理"""
import os
import json
import glob
import hmac
from datetime import datetime
from typing import Literal

import yaml
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline.run import run_pipeline, load_config
from pipeline.finance import HeadhuntDecisionModel
from api.rationale import build_rationale, build_scan_rationale

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "config.yaml")
OUT = os.path.join(BASE, "data", "output")

app = FastAPI(title="猎头用工决策引擎", version="1.0")
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "web")), name="static")


def _board():
    p = os.path.join(OUT, "board.json")
    if not os.path.exists(p):
        raise HTTPException(503, "看板未生成, 先执行一次跑批 (jobs/daily_sync.py)")
    return json.load(open(p, encoding="utf-8"))


def _advisor(aid):
    p = os.path.join(OUT, "advisors", f"{aid}.json")
    if not os.path.exists(p):
        raise HTTPException(404, f"顾问 {aid} 不存在")
    return json.load(open(p, encoding="utf-8"))


@app.get("/")
def index():
    return FileResponse(os.path.join(BASE, "web", "index.html"))


@app.get("/api/board")
def api_board():
    return _board()


@app.get("/api/advisor/{aid}")
def api_advisor(aid: str):
    d = _advisor(aid)
    d["rationale"] = build_rationale(d)
    return d


@app.get("/api/advisor/{aid}/salary_scan")
def api_salary_scan(aid: str, scenario: str = "B"):
    """调薪扫描: 固定产能口径, 扫描年薪 6-30万, 返回 EMPLOY 极限与盈亏平衡
    scenario: A=公司slope / B=外部-0.05 / C=外部-0.05且免波动惩罚
    """
    s = _salary_scan_compute(aid, scenario)
    s["rationale"] = build_scan_rationale(s)
    return s


def _salary_scan_compute(aid: str, scenario: str = "B"):
    d = _advisor(aid)
    cfg = load_config(CONFIG_PATH)
    mcv = d["market_phase"]["market_cv"]
    slope_co = d["market_phase"]["market_slope"]
    if d["market_phase"].get("slope_source") == "external":
        slope_co = -0.3088  # 配置已切外部口径时, A 情景仍用公司斜率参考值
    slope = {"A": slope_co, "B": -0.05, "C": -0.05}.get(scenario.upper(), -0.05)

    cv_eff = d["capacity"].get("cv_used") or d["profile"]["cv"]
    mu = d["profile"]["mu"]
    pipeline_base = (d.get("pipeline") or {}).get("pipeline_base") or 0.0
    hist_base = mu * 4
    base_flow = max(hist_base, pipeline_base)

    tf = 1 + slope * 1.0
    vp = mcv * cv_eff if (mcv > 0.25 and scenario.upper() != "C") else 0.0
    effective = base_flow * max(0.2, tf - vp)
    td = min(0.6, min(0.5, cv_eff * 0.5) + mcv * 0.3)
    capacity = effective * (1 - td)

    hist_q = d.get("quarterly_history", {})
    keys = sorted(hist_q.keys())
    recent4 = [hist_q[k] for k in keys[-4:]] if keys else [0, 0, 0, 0]
    scale = capacity / (mu * 4) if mu > 0 else 0.0
    eq_quarters = [q * scale for q in recent4]

    def run(salary):
        model = HeadhuntDecisionModel(
            discount_rate=cfg["discount_rate"], attrition_rate=cfg["attrition_rate"],
            terminal_multiple=cfg["terminal_multiple"], irr_threshold=cfg["irr_threshold"],
            tiers=[(float(c), float(r)) for c, r in cfg["commission_tiers"]],
            tax_ratio=cfg["tax_ratio"])
        return model.evaluate(
            eq_quarters, cfg["demand_pct"], cfg["competition_pct"], cfg["target_pct"],
            d["insurance_pct"], salary, cfg["lift_pct"], cfg["op_cost_pct"],
            cfg["equity_pct"], cfg["support_cost"], [], datetime.now().year,
            d["overhead_annual"], 0.0, cfg["difficulty_curve"], discount_override=0.0)

    points, max_emp, max_be = [], None, None
    s = 6.0
    while s <= 30.0:
        r = run(s)
        points.append({"salary_annual": round(s, 2), "monthly": round(s * 10000 / 12),
                       "npv_3y": round(r["emp_npv"], 2),
                       "decision": r["decision"],
                       "margin_y1": round(r["emp_margin_y1"], 4)})
        if r["decision"] == "EMPLOY":
            max_emp = s
        if r["emp_npv"] >= 0:
            max_be = s
        s += 0.6

    return {
        "advisor_id": aid, "advisor_name": d["advisor_name"], "scenario": scenario.upper(),
        "slope_used": slope, "capacity_conservative": round(capacity, 2),
        "current_salary_annual": d["salary_annual"],
        "employ_limit_annual": round(max_emp, 2) if max_emp else None,
        "employ_limit_monthly": round(max_emp * 10000 / 12) if max_emp else None,
        "breakeven_annual": round(max_be, 2) if max_be else None,
        "breakeven_monthly": round(max_be * 10000 / 12) if max_be else None,
        "points": points,
    }


class ConfigPatch(BaseModel):
    patch: dict


@app.get("/api/config")
def api_get_config():
    return yaml.safe_load(open(CONFIG_PATH, encoding="utf-8"))


@app.post("/api/config")
def test_update_config(body: ConfigPatch, rerun: bool = True):
    """浅合并顶层/二级键 (如 {"market": {"external_slope": -0.05}}), 改后可选重跑"""
    cfg = yaml.safe_load(open(CONFIG_PATH, encoding="utf-8"))
    for k, v in body.patch.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    result = {"saved": True, "rerun": False}
    if rerun:
        run_pipeline(CONFIG_PATH, use_cache=True)
        result["rerun"] = True
    return result


@app.post("/api/rerun")
def api_rerun(fresh: bool = False):
    """手动触发重算; fresh=true 时重新采集谷露(需配置好凭据)"""
    res = run_pipeline(CONFIG_PATH, use_cache=not fresh)
    return {"ok": True, "n_active": res["meta"]["n_active"],
            "market": res["market"]["phase"], "generated_at": res["board"]["generated_at"]}


@app.post("/api/pipeline/rerun")
def api_pipeline_rerun(fresh: bool = False):
    """网关 executor 约定的 rerun 路径别名 (gateway executor RERUN_PATH)"""
    return api_rerun(fresh)


# ===================== 外部顾问评估 (M3, P1) =====================
import re
from datetime import timezone

from candidate.store import (new_candidate, get as get_candidate,
                             update as update_candidate, list_candidates,
                             validate_token, validate_hr_token, save_json,
                             load_json, derive_status, candidate_workflow_facts,
                             rotate_questionnaire_token, CONFIG_DIR)
from candidate.store import DATA_DIR as CAND_DATA_DIR
from candidate.questionnaire import default_template, validate_template, score_questionnaire
from candidate import engine as cand_engine
from pipeline.loaders import load_salary_map

TEMPLATE_PATH = os.path.join(CONFIG_DIR, "questionnaire_template.json")
# History archive dir, kept next to candidate data (same source as store.DATA_DIR).
DATA_DIR_TEMPLATES = os.path.join(CAND_DATA_DIR, "templates")

# cid format: 'c' + 14-digit timestamp + 4 hex chars; guards path traversal
CID_RE = re.compile(r"^c\d{14}[0-9a-f]{4}$")


def _get_checked(cid):
    if not CID_RE.match(cid):
        raise HTTPException(422, "bad cid format")
    rec = get_candidate(cid)
    if rec is None:
        raise HTTPException(404, f"candidate {cid} not found")
    return rec


def load_template():
    """Current questionnaire template; seeds from default on first call."""
    if not os.path.isfile(TEMPLATE_PATH):
        t = default_template()
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(TEMPLATE_PATH, "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False, indent=1)
        return t
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_template(t):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(TEMPLATE_PATH, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=1)


class IntakeIn(BaseModel):
    name: str
    target_line: str = ""
    notes: str = ""


class SubmitIn(BaseModel):
    answers: dict


class HrAssessIn(BaseModel):
    answers: dict
    interviewer: str = ""


class RotateQuestionnaireIn(BaseModel):
    role: Literal["self", "hr"]


def _verify_internal_token(x_headhunt_internal_token: str = Header(default="")):
    expected = os.environ.get("HEADHUNT_INTERNAL_SECRET", "").strip()
    supplied = str(x_headhunt_internal_token or "")
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "internal_auth_required")


def _token_http_error(reason):
    return HTTPException(410 if reason in ("expired", "already_submitted") else 404, reason)


@app.post("/api/candidate/intake")
def api_candidate_intake(body: IntakeIn):
    if not body.name.strip():
        raise HTTPException(422, "name required")
    rec = new_candidate(body.name.strip(), body.target_line, body.notes)
    return {"cid": rec["cid"], "name": rec["name"], "status": rec["status"],
            "self_url": f"/q/{rec['token']}", "expires_at": rec["token_expires_at"],
            "hr_url": f"/h/{rec['hr_token']}"}


@app.get("/q/{token}")
def q_page(token: str):
    # Always serve the page; its JS calls /api/q/{token}/template which returns
    # 410/404 with a reason, rendered as a friendly state. Validating here would
    # show candidates raw JSON instead.
    return FileResponse(os.path.join(BASE, "web", "q.html"))


@app.get("/api/q/{token}/template")
def api_q_template(token: str):
    cid, reason = validate_token(token)
    if not cid:
        raise _token_http_error(reason)
    rec = get_candidate(cid)
    return {"candidate_name": rec["name"], "expires_at": rec["token_expires_at"],
            "template": load_template()}


@app.post("/api/q/{token}/submit")
def api_q_submit(token: str, body: SubmitIn):
    cid, reason = validate_token(token)
    if not cid:
        raise _token_http_error(reason)
    result = score_questionnaire(load_template(), body.answers, "self")
    save_json(cid, "self_assess.json", {"scored": result, "answers": body.answers})
    update_candidate(cid, self_submitted_at=datetime.now(timezone.utc).isoformat(),
                     status="SELF_DONE")
    return {"ok": True, "status": "SELF_DONE"}


@app.get("/h/{token}")
def h_page(token: str):
    # Same always-serve pattern as q_page: the JS calls /api/h/{token}/template
    # which reports 410/404 with a reason, rendered as a friendly state.
    return FileResponse(os.path.join(BASE, "web", "hr.html"))


@app.get("/api/h/{token}/template")
def api_h_template(token: str):
    cid, reason = validate_hr_token(token)
    if not cid:
        raise _token_http_error(reason)
    rec = get_candidate(cid)
    return {"candidate_name": rec["name"], "expires_at": rec["hr_token_expires_at"],
            "template": load_template()}


@app.post("/api/h/{token}/submit")
def api_h_submit(token: str, body: HrAssessIn):
    # Token-gated equivalent of /api/candidate/{cid}/hr-assess (same archive shape).
    cid, reason = validate_hr_token(token)
    if not cid:
        raise _token_http_error(reason)
    result = score_questionnaire(load_template(), body.answers, "hr")
    save_json(cid, "hr_assess.json",
              {"scored": result, "answers": body.answers, "interviewer": body.interviewer,
               "submitted_at": datetime.now(timezone.utc).isoformat()})
    update_candidate(cid, hr_submitted_at=datetime.now(timezone.utc).isoformat(),
                     status="HR_DONE")
    return {"ok": True, "status": derive_status(get_candidate(cid))}


@app.post("/api/candidate/{cid}/hr-assess")
def api_hr_assess(cid: str, body: HrAssessIn):
    _get_checked(cid)
    result = score_questionnaire(load_template(), body.answers, "hr")
    save_json(cid, "hr_assess.json",
              {"scored": result, "answers": body.answers, "interviewer": body.interviewer,
               "submitted_at": datetime.now(timezone.utc).isoformat()})
    update_candidate(cid, hr_submitted_at=datetime.now(timezone.utc).isoformat(),
                     status="HR_DONE")
    return {"ok": True, "status": derive_status(get_candidate(cid))}


@app.get("/api/candidates")
def api_candidates():
    return {"candidates": list_candidates()}


@app.get("/api/candidate/{cid}")
def api_candidate_detail(cid: str):
    rec = _get_checked(cid)
    rec["status"] = derive_status(rec)
    public_profile = {
        key: value
        for key, value in rec.items()
        if key not in ("token", "hr_token")
    }
    latest = None
    for fname in sorted(os.listdir(store_dir(cid)), reverse=True):
        if fname.startswith("assessment_") and fname.endswith(".json"):
            latest = load_json(cid, fname)
            break
    facts = candidate_workflow_facts(cid)
    return {"profile": public_profile,
            "self_assess": load_json(cid, "self_assess.json"),
            "hr_assess": load_json(cid, "hr_assess.json"),
            "latest_assessment": latest,
            "completion": facts["completion"],
            "source_versions": facts["source_versions"],
            "questionnaire": facts["questionnaire"],
            "latest_assessment_version_id": None}


@app.post("/api/internal/candidate/{cid}/questionnaire-token/rotate")
def api_rotate_questionnaire_token(
    cid: str,
    body: RotateQuestionnaireIn,
    x_headhunt_internal_token: str = Header(default=""),
):
    _verify_internal_token(x_headhunt_internal_token)
    _get_checked(cid)
    try:
        rotated = rotate_questionnaire_token(cid, body.role)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    prefix = "/q/" if body.role == "self" else "/h/"
    return {
        "cid": cid,
        "role": body.role,
        "url": prefix + rotated["token"],
        "expires_at": rotated["expires_at"],
    }


def store_dir(cid):
    from candidate.store import CANDIDATES_DIR
    return os.path.join(CANDIDATES_DIR, cid)


def _internal_samples():
    """salary CSV x grade map -> {grade: [monthly,...]} for salary_band()."""
    csv_path = os.environ.get("HEADHUNT_SALARY_CSV")
    if not csv_path:
        cfg = yaml.safe_load(open(CONFIG_PATH, encoding="utf-8"))
        csv_path = os.path.join(BASE, cfg["data"]["salary_csv"])
    if not os.path.isfile(csv_path):
        return {}
    hr_cfg = (yaml.safe_load(open(CONFIG_PATH, encoding="utf-8")) or {}).get("hr", {})
    salary_map, _skipped = load_salary_map(
        csv_path,
        departed_names=hr_cfg.get("departed_names", []),
        salary_overrides=hr_cfg.get("salary_overrides"))
    grade_map_path = os.path.join(CONFIG_DIR, "candidate_grade_map.json")
    grade_map = {}
    if os.path.isfile(grade_map_path):
        grade_map = json.load(open(grade_map_path, encoding="utf-8")).get("mapping", {})
    return cand_engine.load_internal_samples(salary_map, grade_map)


def _anchors():
    p = os.path.join(CONFIG_DIR, "market_anchors.json")
    if os.path.isfile(p):
        return json.load(open(p, encoding="utf-8")).get("anchors", {})
    return {}


@app.post("/api/candidate/{cid}/assess")
def api_candidate_assess(cid: str):
    _get_checked(cid)
    self_a = load_json(cid, "self_assess.json")
    hr_a = load_json(cid, "hr_assess.json")
    if not self_a or not hr_a:
        raise HTTPException(409, f"questionnaires incomplete: "
                                 f"self={'yes' if self_a else 'no'}, hr={'yes' if hr_a else 'no'}")
    out = cand_engine.assess({"self": self_a["scored"], "hr": hr_a["scored"],
                              "internal_samples": _internal_samples(), "anchors": _anchors()})
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_json(cid, f"assessment_{ts}.json", out)
    update_candidate(cid, assessed_at=datetime.now(timezone.utc).isoformat(),
                     status="ASSESSED")
    return out


@app.get("/api/template")
def api_template_get():
    return load_template()


@app.get("/template")
def template_page():
    return FileResponse(os.path.join(BASE, "web", "template.html"))


@app.put("/api/template")
def api_template_put(t: dict):
    errors = validate_template(t)
    if errors:
        raise HTTPException(422, errors)
    old = load_template()
    t = dict(t)
    t["version"] = old.get("version", 1) + 1   # server-controlled, never trust client
    os.makedirs(os.path.join(DATA_DIR_TEMPLATES), exist_ok=True)
    with open(os.path.join(DATA_DIR_TEMPLATES, f"v{old.get('version', 1)}.json"),
              "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False, indent=1)
    save_template(t)
    return {"saved": True, "version": t["version"]}


# ---------- HR config: grade map + market anchors (M3, P1.5) ----------

from candidate.engine import GRADE_INDEX  # noqa: E402  (appended block, see note above)

GRADE_MAP_PATH = os.path.join(CONFIG_DIR, "candidate_grade_map.json")
ANCHORS_PATH = os.path.join(CONFIG_DIR, "market_anchors.json")
_GRADE_MAP_COMMENT = ("HR-maintained advisor->grade mapping for external-candidate "
                      "salary bands. name must match salary_detail.csv.")
_ANCHORS_COMMENT = "HR-maintained per-grade market monthly-salary anchors {grade:{p25,p50,p75}}."


def _read_config_json(path, comment):
    """Read a {.., "_comment": ..} HR config JSON; None when the file is absent.

    Files ship as committed empty defaults; when missing (fresh volume) the
    PUT handlers recreate them via the `or {}` fallback, so no seeding here.
    """
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class GradeMapIn(BaseModel):
    mapping: dict


class AnchorsIn(BaseModel):
    anchors: dict


@app.get("/grades")
def grades_page():
    return FileResponse(os.path.join(BASE, "web", "grades.html"))


@app.get("/api/hr-config")
def api_hr_config_get():
    gm = _read_config_json(GRADE_MAP_PATH, _GRADE_MAP_COMMENT)
    an = _read_config_json(ANCHORS_PATH, _ANCHORS_COMMENT)
    return {"grade_map": gm.get("mapping", {}) if gm else {},
            "anchors": an.get("anchors", {}) if an else {},
            "grades": [g for g in GRADE_INDEX]}


@app.put("/api/hr-config/grade-map")
def api_hr_config_grade_map(body: GradeMapIn):
    for name, grade in body.mapping.items():
        if not isinstance(name, str) or not name.strip():
            raise HTTPException(422, f"bad name: {name!r}")
        if grade not in GRADE_INDEX:
            raise HTTPException(422, f"unknown grade {grade!r}; valid: {[g for g in GRADE_INDEX]}")
    doc = _read_config_json(GRADE_MAP_PATH, _GRADE_MAP_COMMENT) or {}
    doc["_comment"] = _GRADE_MAP_COMMENT
    doc["mapping"] = body.mapping
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(GRADE_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    return {"saved": True, "n": len(body.mapping)}


@app.put("/api/hr-config/anchors")
def api_hr_config_anchors(body: AnchorsIn):
    for grade, band in body.anchors.items():
        if grade not in GRADE_INDEX:
            raise HTTPException(422, f"unknown grade {grade!r}")
        if not isinstance(band, dict) or set(band) != {"p25", "p50", "p75"}:
            raise HTTPException(422, f"band for {grade} must have exactly p25/p50/p75")
        for k, v in band.items():
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
                raise HTTPException(422, f"band {grade}.{k} must be a positive number")
    doc = _read_config_json(ANCHORS_PATH, _ANCHORS_COMMENT) or {}
    doc["_comment"] = _ANCHORS_COMMENT
    doc["anchors"] = body.anchors
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(ANCHORS_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    return {"saved": True, "n": len(body.anchors)}
