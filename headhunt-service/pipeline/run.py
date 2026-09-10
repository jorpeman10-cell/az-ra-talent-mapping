# -*- coding: utf-8 -*-
"""管线单入口: run_pipeline(config_path) -> 完整结果 dict
采集 -> 清洗 -> 计算 -> 输出 board.json + advisors/*.json
"""
import os
import json
import math
from datetime import datetime

import yaml
from dotenv import load_dotenv

from .collect import collect_all
from .cleaning import clean_quarterly_revenue, clean_company_summary, compute_self_ratio
from .cleaning import quarterly_active_clients, deals_last_12m
from .loaders import load_salary_map, load_cost_map
from .engine import (calculate_advisor_profile, determine_market_phase,
                     calculate_effective_capacity, evaluate_advisor,
                     rank_advisors, get_last_n_quarters)


def load_config(config_path):
    cfg = yaml.safe_load(open(config_path, encoding="utf-8"))
    env_path = os.path.join(os.path.dirname(config_path), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    flat = {**cfg["finance"],
            "commission_tiers": cfg["commission_tiers"],
            "external_slope": cfg["market"].get("external_slope"),
            "difficulty_curve": {int(k): float(v) for k, v in cfg["difficulty_curve"].items()},
            "overhead_mode": cfg["cost"]["overhead_mode"],
            "default_salary_annual": cfg["cost"]["default_salary_annual"],
            "default_insurance_pct": cfg["cost"]["default_insurance_pct"],
            "default_overhead_annual": cfg["cost"]["default_overhead_annual"],
            "departed_names": frozenset(cfg.get("hr", {}).get("departed_names", [])),
            "salary_overrides": dict(cfg.get("hr", {}).get("salary_overrides", {}) or {}),
            "risk": cfg.get("risk", {}),
            "since": cfg["collect"]["since"],
            "paths": cfg["data"]}
    return flat


def _base_dir(config_path):
    return os.path.dirname(os.path.dirname(os.path.abspath(config_path)))


def build_activity_map(activity_rows, now, join_dates=None):
    """面试/推荐活动 -> {advisor_id: {itv_cv, itv_qoq, itv_mean, rec_cv}}

    itv_cv/itv_qoq: 面试口径波动与动量（原有）
    itv_mean: 面试季均值（场/季）
    rec_cv: 推荐量季度 CV（实证：推荐量波动预测回款波动 ρ=+0.57，进 CV 先验）

    join_dates: {advisor_id: joinInDate} — 窗口从入职季度起算；
    入职前的季度不计零（否则新人的活动 CV 被预入职零值严重高估）。
    """
    if not activity_rows:
        return {}
    join_dates = join_dates or {}

    def _join_idx(aid):
        jd = join_dates.get(aid)
        if not jd:
            return None
        try:
            d = datetime.fromisoformat(str(jd)[:10])
            return d.year * 4 + (d.month - 1) // 3 + 1
        except ValueError:
            return None

    def _series(rows):
        m = {}
        for r in rows:
            m.setdefault(str(r["advisor_id"]), {})[(int(r["year"]), int(r["quarter"]))] = int(r["cnt"])
        return m

    itv = _series(activity_rows.get("interview", []))
    rec = _series(activity_rows.get("recommend", []))
    cur_y, cur_q = now.year, (now.month - 1) // 3 + 1

    def qidx(yq): return yq[0] * 4 + yq[1]
    def fromidx(i): return (i // 4, i % 4) if i % 4 else (i // 4 - 1, 4)

    end = qidx((cur_y, cur_q))

    def _stats(aid, qm, min_total=8):
        start = end - 7
        ji = _join_idx(aid)
        if ji is not None:
            start = max(start, ji)
        series = [qm.get(fromidx(i), 0) for i in range(start, end + 1)]
        total = sum(series)
        if total < min_total:
            return None, 0.0, 0.0
        m = total / len(series)
        sd = math.sqrt(sum((x - m) ** 2 for x in series) / len(series))
        return (round(sd / m, 4) if m > 0 else None), round(m, 2), 0.0

    out = {}
    for aid in set(itv) | set(rec):
        itv_cv, itv_mean, _ = _stats(aid, itv.get(aid, {}))
        rec_cv, _, _ = _stats(aid, rec.get(aid, {}))
        series = [itv.get(aid, {}).get(fromidx(i), 0) for i in range(end - 7, end + 1)]
        recent2, prev2 = sum(series[-2:]), sum(series[-4:-2])
        qoq = (recent2 - prev2) / prev2 if prev2 > 0 else 0.0
        out[aid] = {"itv_cv": itv_cv, "itv_qoq": round(qoq, 4),
                    "itv_mean": itv_mean, "rec_cv": rec_cv}
    return out


def run_pipeline(config_path, use_cache=True, as_of=None):
    cfg = load_config(config_path)
    base = _base_dir(config_path)
    P = {k: os.path.join(base, v) for k, v in cfg["paths"].items()}
    now = as_of or datetime.now()
    current_year = now.year

    # ---- 采集/缓存 ----
    raw = None
    if use_cache and os.path.exists(P["raw_cache"]):
        raw = json.load(open(P["raw_cache"], encoding="utf-8"))
    if raw is None or "F" not in raw:
        raw = collect_all(cfg["since"])
        json.dump(raw, open(P["raw_cache"], "w", encoding="utf-8"),
                  ensure_ascii=False, default=str)
    # 活动数据: 新版采集自带 raw["activity"]; 旧缓存读 activity_cache
    activity_rows = raw.get("activity")
    if activity_rows is None and os.path.exists(P["activity_cache"]):
        activity_rows = json.load(open(P["activity_cache"], encoding="utf-8"))
    elif activity_rows is not None:
        json.dump(activity_rows, open(P["activity_cache"], "w", encoding="utf-8"),
                  ensure_ascii=False, default=str)

    # ---- 清洗 ----
    advisors = clean_quarterly_revenue(raw["A"], as_of=now)
    master = {str(a["advisor_id"]): a for a in raw["advisors"]}
    for aid, adv in advisors.items():
        m = master.get(aid)
        if m:
            adv["db_status"] = m["status"]
            if m["status"] != "Active":
                adv["status"] = "INACTIVE"
    company_series = clean_company_summary(raw["D"])
    self_ratio = compute_self_ratio(raw["B"])

    # ---- 新人通道: Active 且无回款历史、但有签约管道的顾问, 以管道口径进看板 ----
    # (如魏菲: 临床转市场、入职以来无回款归属, 但有 2 个 Accepted Offer)
    pipeline_ids = {str(f_["advisor_id"]) for f_ in raw.get("F", [])
                    if float(f_.get("signed_12m_wan") or 0) > 0}
    for aid, m in master.items():
        if aid in advisors or m.get("status") != "Active" or aid not in pipeline_ids:
            continue
        advisors[aid] = {
            "name": m.get("advisor_name") or aid,
            "quarters": {},
            "status": "ACTIVE",
            "first_quarter": None,
            "last_quarter": None,
            "n_quarters": 0,
            "new_hire_channel": True,
        }

    # ---- 市场 ----
    market = determine_market_phase(company_series, external_slope=cfg["external_slope"])

    # ---- 表E 校准记录 (谷露目标表无年份, 样本不足时引擎回退默认cap) ----
    cur_year_budget = sum(float(e["target_wan"]) for e in raw["E_raw"]
                          if master.get(str(e["advisor_id"]), {}).get("status") == "Active")
    cur_year_actual = sum(s["total_revenue"] for s in company_series if s["year"] == current_year)
    history_records = ([{"year": current_year, "annualized": cur_year_budget,
                         "actual": cur_year_actual}]
                       if cur_year_budget > 0 and cur_year_actual > 0 else [])

    # ---- 外部数据 ----
    salary_map, salary_skipped = load_salary_map(
        P["salary_csv"], departed_names=cfg["departed_names"],
        salary_overrides=cfg["salary_overrides"])
    cost_map, cost_skipped = load_cost_map(
        P["cost_xlsx"], overhead_mode=cfg["overhead_mode"],
        departed_names=cfg["departed_names"])
    activity_map = build_activity_map(
        activity_rows, now,
        join_dates={str(a["advisor_id"]): a.get("joinInDate") for a in raw["advisors"]})
    pipeline_map = {}
    for f_ in raw.get("F", []):
        rec, stale = float(f_["received_cnt"] or 0), float(f_["stale_unpaid_cnt"] or 0)
        prob = rec / (rec + stale) if rec + stale > 0 else 0.9
        pipeline_map[str(f_["advisor_id"])] = {
            "signed_12m_wan": float(f_["signed_12m_wan"] or 0),
            "collection_prob": round(prob, 3),
            "outlier_cnt": int(f_.get("outlier_cnt") or 0)}

    # ---- 逐顾问决策 ----
    client_q_map = quarterly_active_clients(raw.get("C", []))
    deals_map = deals_last_12m(raw.get("C", []), as_of=now)
    COMPANY_MEDIAN_DEAL_PRICE = 42.9  # 万/单（C 表客单价中位数, 2026-09 实证; 无成单新人的 M 估计分母）
    decisions = []
    for aid, adv in advisors.items():
        profile = calculate_advisor_profile(aid, adv["quarters"], company_series,
                                            self_ratio=self_ratio.get(aid))
        pl = pipeline_map.get(aid)
        act = activity_map.get(aid)
        deals_12m = deals_map.get(aid)
        if not deals_12m and pl and pl.get("signed_12m_wan"):
            # 新人通道: C 表无成单记录时, 用在途签约额 ÷ 公司客单价中位数估计 M;
            # 下限 1.0——先验回归训练范围 M∈[3,24], 不外推到更低(子任务 8.4 警示)
            deals_12m = max(1.0, pl["signed_12m_wan"] / COMPANY_MEDIAN_DEAL_PRICE)
        capacity = calculate_effective_capacity(
            profile, market, pipeline=pl, activity=act,
            deals_12m=deals_12m,
            client_series=client_q_map.get(aid),
            risk=cfg.get("risk"))
        recent4 = get_last_n_quarters(adv["quarters"], 4)

        ecfg = {"discount_rate": cfg["discount_rate"], "attrition_rate": cfg["attrition_rate"],
                "terminal_multiple": cfg["terminal_multiple"], "irr_threshold": cfg["irr_threshold"],
                "commission_tiers": cfg["commission_tiers"], "tax_ratio": cfg["tax_ratio"],
                "demand_pct": cfg["demand_pct"], "competition_pct": cfg["competition_pct"],
                "target_pct": cfg["target_pct"], "lift_pct": cfg["lift_pct"],
                "op_cost_pct": cfg["op_cost_pct"], "equity_pct": cfg["equity_pct"],
                "support_cost": cfg["support_cost"],
                "salary_annual": cfg["default_salary_annual"],
                "insurance_pct": cfg["default_insurance_pct"],
                "company_fixed_cost": cfg["default_overhead_annual"],
                "management_cost": 0.0}
        s = salary_map.get(adv["name"])
        if s:
            ecfg["salary_annual"] = s["salary_annual"]
        cost = cost_map.get(adv["name"])
        if cost:
            ecfg["insurance_pct"] = cost["insurance_pct"]
            ecfg["company_fixed_cost"] = cost["overhead_annual_wan"]

        d = evaluate_advisor(profile, capacity, market, recent4,
                             history_records, current_year, cfg["difficulty_curve"], ecfg)
        d["advisor_name"] = adv["name"]
        d["status"] = adv["status"]
        d["n_quarters"] = adv["n_quarters"]
        if adv.get("new_hire_channel"):
            d["new_hire_channel"] = True
        d["salary_annual"] = ecfg["salary_annual"]
        d["insurance_pct"] = ecfg["insurance_pct"]
        d["overhead_annual"] = ecfg["company_fixed_cost"]
        d["salary_source"] = "salary_csv" if s else "default"
        d["cost_source"] = "cost_xlsx" if cost else "default"
        if pl:
            d["pipeline"] = {**pl, "base_source": capacity["base_source"],
                             "pipeline_base": capacity["pipeline_base"]}
        d["capacity"]["cv_source"] = capacity.get("cv_source")
        d["capacity"]["cv_used"] = capacity.get("cv_used")
        d["capacity"]["beta_adj"] = capacity.get("beta_adj")
        d["quarterly_history"] = {f"{k[0]}Q{k[1]}": v for k, v in sorted(adv["quarters"].items())}
        d["timestamp"] = now.isoformat()
        decisions.append(d)

    board = rank_advisors([d for d in decisions if d["status"] == "ACTIVE"], market)
    board["generated_at"] = now.isoformat()

    # ---- 落盘 ----
    os.makedirs(P["output_dir"], exist_ok=True)
    os.makedirs(os.path.join(P["output_dir"], "advisors"), exist_ok=True)
    with open(os.path.join(P["output_dir"], "board.json"), "w", encoding="utf-8") as f:
        json.dump(board, f, ensure_ascii=False, indent=1)
    for d in decisions:
        with open(os.path.join(P["output_dir"], "advisors", f"{d['advisor_id']}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)

    return {"board": board, "advisors": decisions, "market": market,
            "config": cfg,
            "meta": {"n_advisors": len(decisions),
                     "n_active": len(board["advisors"]),
                     "salary_skipped": salary_skipped, "cost_skipped": cost_skipped,
                     "budget_wan": cur_year_budget, "actual_ytd_wan": cur_year_actual}}
