# -*- coding: utf-8 -*-
"""外部市场数据情景分析: 公司口径 slope vs 医药行业外部口径 slope
外部依据 (2026-09 检索):
  - 猎聘: 2025营收-4.6%(四连降), 2026H1 +5.6%止跌, 新发职位+14%
  - 科锐国际: 2025猎头相关收入+8.26%
  - 医药行业: 2025全球生物医药裁员4.27万人(+47%), 拐点在2025秋;
    2026Q1裁员33家->Q2 17家; 2026H1生物医药求职+7.7%, AI制药职位+84%
  - 我司客户=MNC药企+国内大型药企: 2025重灾, 2026企稳
  => 外部 slope 估计: 保守 -0.05, 中性 0.00, 乐观 +0.05
"""
import sys, os, json
sys.path.insert(0, r"C:/Users/EDY/Documents/kimi/workspace/headhunt_model")
from step3_cleaning import clean_quarterly_revenue, clean_company_summary, compute_self_ratio
from step4_engine import (calculate_advisor_profile, determine_market_phase,
                          calculate_effective_capacity, evaluate_advisor,
                          get_last_n_quarters, DEFAULT_CONFIG)
from salary_loader import load_salary_map
from step5_run import build_activity_map, DIFFICULTY_CURVE
from datetime import datetime

BASE = os.path.dirname(__file__)
raw = json.load(open(os.path.join(BASE, "raw_cache.json"), encoding="utf-8"))
advisors = clean_quarterly_revenue(raw["A"])
master = {str(a["advisor_id"]): a for a in raw["advisors"]}
company = clean_company_summary(raw["D"])
sr = compute_self_ratio(raw["B"])
sm, _ = load_salary_map()
now = datetime.now()
act_map = build_activity_map(now)

pipeline_map = {}
for f_ in raw["F"]:
    rec, stale = float(f_["received_cnt"] or 0), float(f_["stale_unpaid_cnt"] or 0)
    prob = rec / (rec + stale) if rec + stale > 0 else 0.9
    pipeline_map[str(f_["advisor_id"])] = {
        "signed_12m_wan": float(f_["signed_12m_wan"] or 0), "collection_prob": round(prob, 3)}

mkt_company = determine_market_phase(company)
SCENARIOS = {
    "公司口径(-0.31)": mkt_company["market_slope"],
    "外部保守(-0.05)": -0.05,
    "外部中性(0.00)": 0.00,
    "外部乐观(+0.05)": 0.05,
}

hist = [{"year": 2026, "annualized": 800.0, "actual": 609.0}]

names, results = [], {}
for aid, adv in advisors.items():
    if master.get(aid, {}).get("status") != "Active":
        continue
    prof = calculate_advisor_profile(aid, adv["quarters"], company, self_ratio=sr.get(aid))
    pl = pipeline_map.get(aid)
    act = act_map.get(aid)
    cfg = dict(DEFAULT_CONFIG)
    s = sm.get(adv["name"])
    if s:
        cfg["salary_annual"] = s["salary_annual"]
        cfg["insurance_pct"] = s["insurance_pct"]
    r4 = get_last_n_quarters(adv["quarters"], 4)
    names.append(adv["name"])
    for sc, slope in SCENARIOS.items():
        mkt = dict(mkt_company)
        mkt["market_slope"] = slope
        if mkt["market_cv"] <= 0.25:
            mkt["phase"] = "RISING" if slope > 0.10 else ("FALLING" if slope < -0.10 else "FLAT")
        cap = calculate_effective_capacity(prof, mkt, pipeline=pl, activity=act)
        d = evaluate_advisor(prof, cap, mkt, r4, hist, 2026, DIFFICULTY_CURVE, cfg)
        results.setdefault(sc, {})[adv["name"]] = (cap["conservative"], d["decision"])

hdr = f"{'姓名':<7}" + "".join(f"{sc:>16}" for sc in SCENARIOS)
print(hdr)
for n in names:
    line = f"{n:<7}"
    for sc in SCENARIOS:
        cons, dec = results[sc][n]
        line += f"{f'{cons:.0f}万/{dec[:3]}':>16}"
    print(line)

print()
for sc in SCENARIOS:
    decs = [results[sc][n][1] for n in names]
    print(f"{sc:<14} EMPLOY={decs.count('EMPLOY')}  INCUBATE={decs.count('INCUBATE')}  PASS={decs.count('PASS')}")
