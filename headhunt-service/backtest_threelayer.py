# -*- coding: utf-8 -*-
"""三层风险结构回测: 留出 4 个季度, legacy(单一 CV) vs 三层(L1 收缩+L2 监测) 的产能年化 MAPE.

用法: py -3 backtest_threelayer.py
数据: data/raw_cache.json + data/activity_cache.json（缓存快照, 无需采集）
口径: 预测 = as_of 时点 conservative(年化产能); 实际 = 其后 4 个季度回款合计.
      MAPE = |预测-实际|/实际, 按顾问聚合中位数. 预测为负或零时按相对误差截断在 300%.
"""
import json
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.cleaning import (clean_quarterly_revenue, clean_company_summary,
                               compute_self_ratio, quarterly_active_clients,
                               deals_last_12m)
from pipeline.run import build_activity_map, load_config
from pipeline.engine import (calculate_advisor_profile, determine_market_phase,
                             calculate_effective_capacity)

AS_OF = (2025, 3)  # 留出 2025Q4-2026Q2 共 4 个季度做验证... 注: 缓存到 2026Q2
FWD_QUARTERS = [(2025, 4), (2026, 1), (2026, 2)]


def _slice(raw, activity, as_of):
    y, q = as_of
    a = [r for r in raw["A"] if (int(r["year"]), int(r["quarter"])) <= as_of]
    c = [r for r in raw.get("C", [])
         if not r.get("signDate") or (int(str(r["signDate"])[:4]), (int(str(r["signDate"])[5:7]) - 1) // 3 + 1) <= as_of]
    act = {k: [r for r in v if (int(r["year"]), int(r["quarter"])) <= as_of]
           for k, v in activity.items()}
    d = [s for s in raw["D"] if (int(s["year"]), int(s["quarter"])) <= as_of]
    return {"advisors": raw["advisors"], "A": a, "B": raw.get("B", []), "C": c,
            "D": d, "E_raw": raw.get("E_raw", []), "F": []}, act


def run_mode(raw_s, act_s, as_of, risk_cfg, cfg):
    now = datetime(as_of[0], as_of[1] * 3, 28)
    advisors = clean_quarterly_revenue(raw_s["A"], as_of=now)
    master = {str(a["advisor_id"]): a for a in raw_s["advisors"]}
    for aid, adv in advisors.items():
        m = master.get(aid)
        if m:
            adv["db_status"] = m["status"]
            if m["status"] != "Active":
                adv["status"] = "INACTIVE"
    company = clean_company_summary(raw_s["D"])
    market = determine_market_phase(company, external_slope=None)
    self_ratio = compute_self_ratio(raw_s["B"])
    client_q = quarterly_active_clients(raw_s["C"])
    deals = deals_last_12m(raw_s["C"], as_of=now)
    act_map = build_activity_map(act_s, now)
    out = {}
    for aid, adv in advisors.items():
        profile = calculate_advisor_profile(aid, adv["quarters"], company,
                                            self_ratio=self_ratio.get(aid))
        cap = calculate_effective_capacity(
            profile, market, pipeline=None, activity=act_map.get(aid),
            deals_12m=deals.get(aid),
            client_series=client_q.get(aid),
            risk=risk_cfg)
        out[aid] = cap["conservative"]
    return out


def actual_fwd(raw, as_of, fwd):
    agg = {}
    for r in raw["A"]:
        key = (int(r["year"]), int(r["quarter"]))
        if key in fwd:
            agg[str(r["advisor_id"])] = agg.get(str(r["advisor_id"]), 0.0) + float(r["revenue"] or 0)
    return agg


def mape(pairs):
    errs = []
    for pred, act in pairs:
        if act <= 0:
            continue
        errs.append(min(3.0, abs(pred - act) / act))
    return round(sum(errs) / len(errs), 4) if errs else None, len(errs)


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    raw = json.load(open(os.path.join(base, "data", "raw_cache.json"), encoding="utf-8"))
    activity = json.load(open(os.path.join(base, "data", "activity_cache.json"), encoding="utf-8"))
    cfg = load_config(os.path.join(base, "config", "config.yaml"))

    raw_s, act_s = _slice(raw, activity, AS_OF)
    actual = actual_fwd(raw, AS_OF, FWD_QUARTERS)

    legacy = run_mode(raw_s, act_s, AS_OF, {"enabled": False}, cfg)
    three = run_mode(raw_s, act_s, AS_OF, cfg["risk"], cfg)

    diff_advisors = [a for a in actual
                     if a in legacy and a in three and abs(legacy[a] - three[a]) > 0.5]
    print(f"行为不同的顾问({len(diff_advisors)}个):", diff_advisors)
    for a in diff_advisors:
        print(f"  {a}: legacy={legacy[a]:.1f} three={three[a]:.1f} actual={actual.get(a, 0):.1f}")

    pairs_legacy = [(legacy[a], v) for a, v in actual.items() if a in legacy and v >= 5]
    pairs_three = [(three[a], v) for a, v in actual.items() if a in three and v >= 5]

    m1, n1 = mape(pairs_legacy)
    m2, n2 = mape(pairs_three)
    print(f"as_of={AS_OF} 前瞻 3 季度(缓存末端限制)")
    print(f"legacy 单一 CV:      MAPE={m1} (n={n1})")
    print(f"三层(L1+L2):         MAPE={m2} (n={n2})")
    print("明细(三层 vs 实际, 误差最大的 6 个):")
    rows = sorted(((a, three[a], actual[a]) for a in actual if a in three and actual[a] >= 5),
                  key=lambda x: -abs(x[1] - x[2]) / x[2])[:6]
    for a, p, v in rows:
        print(f"  advisor {a}: pred={p:.1f} actual={v:.1f} err={abs(p - v) / v:.0%}")


if __name__ == "__main__":
    main()
