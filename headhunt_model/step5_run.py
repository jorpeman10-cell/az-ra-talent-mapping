# -*- coding: utf-8 -*-
"""
主编排: 采集(step2) -> 清洗(step3) -> 计算(step4) -> 输出(第五章)
用法: py -3 step5_run.py [--top N]
"""
import sys, json, argparse
from datetime import datetime
sys.path.insert(0, r"C:/Users/EDY/Documents/kimi/workspace/headhunt_model")

from step2_collect import collect_all
from step3_cleaning import clean_quarterly_revenue, clean_company_summary, compute_self_ratio
from step4_engine import (calculate_advisor_profile, determine_market_phase,
                          calculate_effective_capacity, evaluate_advisor,
                          rank_advisors, get_last_n_quarters, DEFAULT_CONFIG)
from salary_loader import load_salary_map
from cost_loader import load_cost_map

OUT_DIR = r"C:/Users/EDY/Documents/kimi/workspace/headhunt_model/output"
ACT_CACHE = r"C:/Users/EDY/Documents/kimi/workspace/headhunt_model/activity_cache.json"


def build_activity_map(now):
    """面试活动 -> {advisor_id: {itv_cv, itv_qoq}}
    itv_cv: 近8个日历季度面试数的CV (总场次<8视为样本不足 -> None, 回退回款CV)
    itv_qoq: 近2季面试数 vs 之前2季 的环比 (prev=0时记0)
    """
    import os, math
    if not os.path.exists(ACT_CACHE):
        return {}
    act = json.load(open(ACT_CACHE, encoding="utf-8"))
    itv = {}
    for r in act["interview"]:
        itv.setdefault(str(r["advisor_id"]), {})[(int(r["year"]), int(r["quarter"]))] = int(r["cnt"])
    cur_y, cur_q = now.year, (now.month - 1) // 3 + 1

    def qidx(yq): return yq[0] * 4 + yq[1]
    def fromidx(i): return (i // 4, i % 4) if i % 4 else (i // 4 - 1, 4)

    end = qidx((cur_y, cur_q))
    out = {}
    for aid, qm in itv.items():
        series = [qm.get(fromidx(i), 0) for i in range(end - 7, end + 1)]
        total = sum(series)
        if total < 8:
            out[aid] = {"itv_cv": None, "itv_qoq": 0.0, "itv_total_8q": total}
            continue
        m = total / 8
        sd = math.sqrt(sum((x - m) ** 2 for x in series) / 8)
        recent2, prev2 = sum(series[-2:]), sum(series[-4:-2])
        qoq = (recent2 - prev2) / prev2 if prev2 > 0 else 0.0
        out[aid] = {"itv_cv": round(sd / m, 4) if m > 0 else None,
                    "itv_qoq": round(qoq, 4), "itv_total_8q": total}
    return out

# 难度趋势曲线(管理后台配置项, v1 用平坦曲线)
DIFFICULTY_CURVE = {2023: 1.0, 2024: 1.0, 2025: 1.05, 2026: 1.10, 2027: 1.15, 2028: 1.2, 2029: 1.25}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=0, help="只输出排名前N的顾问详情(0=全部)")
    ap.add_argument("--cached", action="store_true", help="使用 raw_cache.json 离线运行")
    args = ap.parse_args()

    now = datetime.now()
    current_year = now.year
    print(f"[1/4] 采集数据 (as of {now:%Y-%m-%d %H:%M}) ...")
    import os
    cache_path = os.path.join(os.path.dirname(__file__), "raw_cache.json")
    if args.cached and os.path.exists(cache_path):
        raw = json.load(open(cache_path, encoding="utf-8"))
        print("  (使用 raw_cache.json 缓存)")
        if "F" not in raw:
            print("  缓存缺少表F(在途管道), 重新采集 ...")
            raw = collect_all()
            json.dump(raw, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, default=str)
    else:
        raw = collect_all()
        json.dump(raw, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, default=str)
    print(f"  表A 回款分摊: {len(raw['A'])} 行 | 表B 客户: {len(raw['B'])} 行 | "
          f"表C 项目明细: {len(raw['C'])} 行 | 表E 年度目标: {len(raw['E_raw'])} 行 | "
          f"表F 在途管道: {len(raw.get('F', []))} 行")

    print("[2/4] 清洗 ...")
    advisors = clean_quarterly_revenue(raw["A"], as_of=now)
    # 用谷露 user 表的真实状态覆盖推断状态 (Active/Leave/Inactive)
    master = {str(a["advisor_id"]): a for a in raw["advisors"]}
    for aid, adv in advisors.items():
        m = master.get(aid)
        if m:
            adv["db_status"] = m["status"]
            if m["status"] != "Active":
                adv["status"] = "INACTIVE"
            elif adv["status"] == "ACTIVE":
                adv["status"] = "ACTIVE"
    # 表D由清洗后的A聚合, 与库内invoice总额交叉验证
    company_series = clean_company_summary(raw["D"])
    self_ratio = compute_self_ratio(raw["B"])
    active = {k: v for k, v in advisors.items() if v["status"] == "ACTIVE"}
    print(f"  顾问 {len(advisors)} 人 (ACTIVE {len(active)}), 公司序列 {len(company_series)} 个季度")

    print("[3/4] 计算市场阶段 + 顾问决策 ...")
    market = determine_market_phase(company_series)
    print(f"  市场阶段: {market['phase']}  slope={market['market_slope']}  cv={market['market_cv']}")

    # 表E: 谷露目标表无年份 -> 仅构造当前年度 budget vs actual;
    # 无多年历史, irr20 calibration 样本不足自动回退 cap=0.3
    cur_year_budget = sum(e["target_wan"] for e in raw["E_raw"]
                          if master.get(str(e["advisor_id"]), {}).get("status") == "Active")
    cur_year_actual = sum(s["total_revenue"] for s in company_series if s["year"] == current_year)
    history_records = []
    if cur_year_budget > 0 and cur_year_actual > 0:
        history_records = [{"year": current_year, "annualized": cur_year_budget,
                            "actual": cur_year_actual}]
    print(f"  表E 当前年在职目标合计 {cur_year_budget:.0f}万, 实际(YTD) {cur_year_actual:.0f}万")

    decisions = []
    salary_map, salary_skipped = load_salary_map()
    if salary_skipped:
        print(f"  薪资表跳过: {salary_skipped}")
    cost_map, cost_skipped = load_cost_map()
    if cost_skipped:
        print(f"  成本表跳过: {cost_skipped}")
    n_cost_hit = 0
    n_salary_hit = 0
    # 表F: 在途管道 map (collection_prob = 已回款 / (已回款 + 疑似坏账))
    pipeline_map = {}
    for f_ in raw.get("F", []):
        rec, stale = float(f_["received_cnt"] or 0), float(f_["stale_unpaid_cnt"] or 0)
        prob = rec / (rec + stale) if (rec + stale) > 0 else 0.9
        pipeline_map[str(f_["advisor_id"])] = {
            "signed_12m_wan": float(f_["signed_12m_wan"] or 0),
            "collection_prob": round(prob, 3),
            "outlier_cnt": int(f_.get("outlier_cnt") or 0),
        }
    n_pipeline_hit = 0
    activity_map = build_activity_map(now)
    n_cv_itv = 0
    for aid, adv in advisors.items():
        profile = calculate_advisor_profile(aid, adv["quarters"], company_series,
                                            self_ratio=self_ratio.get(aid))
        pl = pipeline_map.get(aid)
        act = activity_map.get(aid)
        capacity = calculate_effective_capacity(profile, market, pipeline=pl, activity=act)
        if pl and capacity.get("base_source") == "pipeline":
            n_pipeline_hit += 1
        if capacity.get("cv_source") == "interview":
            n_cv_itv += 1
        recent4 = get_last_n_quarters(adv["quarters"], 4)
        cfg = dict(DEFAULT_CONFIG)
        s = salary_map.get(adv["name"])
        if s:
            cfg["salary_annual"] = s["salary_annual"]
            cfg["insurance_pct"] = s["insurance_pct"]
            n_salary_hit += 1
        cost = cost_map.get(adv["name"])
        if cost:
            # 社保率与公摊以成本拆分xlsx为准(与salary_detail不一致时xlsx优先)
            cfg["insurance_pct"] = cost["insurance_pct"]
            cfg["company_fixed_cost"] = cost["overhead_annual_wan"]
            cfg["management_cost"] = 0.0
            n_cost_hit += 1
        d = evaluate_advisor(profile, capacity, market, recent4,
                             history_records, current_year, DIFFICULTY_CURVE, cfg)
        d["salary_annual"] = cfg["salary_annual"]
        d["salary_source"] = "salary_detail.csv" if s else "default_18w"
        d["cost_source"] = cost["source"] if cost else "default_13w_overhead"
        if cost:
            d["overhead_annual"] = cost["overhead_annual_wan"]
            d["total_cost_annual_actual"] = cost["total_cost_annual_wan"]
        if pl:
            d["pipeline"] = {**pl, "base_source": capacity["base_source"],
                             "pipeline_base": capacity["pipeline_base"]}
        d["capacity"]["cv_source"] = capacity.get("cv_source")
        d["capacity"]["cv_used"] = capacity.get("cv_used")
        d["capacity"]["itv_qoq"] = capacity.get("itv_qoq")
        d["advisor_name"] = adv["name"]
        d["status"] = adv["status"]
        d["n_quarters"] = adv["n_quarters"]
        decisions.append(d)
    print(f"  薪资匹配: {n_salary_hit}/{len(advisors)} 人使用真实薪资; "
          f"成本表命中: {n_cost_hit} 人; 管道修正: {n_pipeline_hit} 人; 面试CV接管: {n_cv_itv} 人")

    print("[4/4] 输出 ...")
    board = rank_advisors([d for d in decisions if d["status"] == "ACTIVE"], market)

    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M")
    for d in decisions:
        d["timestamp"] = now.isoformat()

    board_path = f"{OUT_DIR}/ranking_board_{stamp}.json"
    with open(board_path, "w", encoding="utf-8") as f:
        json.dump(board, f, ensure_ascii=False, indent=1)
    print(f"  排名看板 -> {board_path}")

    detail_list = decisions if not args.top else \
        sorted(decisions, key=lambda x: -x["capacity"]["conservative"])[: args.top]
    for d in detail_list:
        p = f"{OUT_DIR}/advisor_{d['advisor_id']}_{d['advisor_name']}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)

    # 控制台摘要
    print("\n===== 批量排名 (ACTIVE顾问) =====")
    print(f"{'排名':<4}{'姓名':<10}{'mu':>7}{'CV':>7}{'beta':>7}{'保守产能':>9}{'年薪(万)':>9}  {'决策':<9}{'score':>7}")
    for i, a in enumerate(board["advisors"], 1):
        dx = next(x for x in decisions if x["advisor_id"] == a["advisor_id"])
        prof = dx["profile"]
        print(f"{i:<4}{a['name']:<10}{prof['mu']:>7}{prof['cv']:>7}{a['beta']:>7}"
              f"{a['conservative']:>9}{dx['salary_annual']:>9}  {a['decision']:<9}{a['rank_score']:>7}")


if __name__ == "__main__":
    main()
