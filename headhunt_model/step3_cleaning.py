# -*- coding: utf-8 -*-
"""
第三章 数据清洗与预处理逻辑
输入: step2 采集的原始 DataFrame / list[dict]
输出: 清洗后的标准格式 (advisor_quarterly, company_quarterly, ...)
"""
import math
from datetime import datetime, timedelta

AMOUNT_UNIT = 10000.0  # 元 -> 万


# ---------- 3.1 顾问季度回款清洗 ----------

def clean_quarterly_revenue(raw_rows, as_of=None):
    """
    raw_rows: [{advisor_id, advisor_name, year, quarter, revenue(万), hire_date?}, ...]
    返回: {advisor_id: {"name":..., "quarters": {(y,q): revenue}, "status": ACTIVE/INACTIVE,
                        "first_quarter": (y,q), "last_quarter": (y,q)}}
    规则:
      1. 3sigma 异常值 -> 相邻季度线性插值替代, 并标记
      2. 缺失季度补 0 (在顾问首个季度~当前季度范围内)
      3. 金额统一为万, 2位小数
      4. 入职 < 2个季度的顾问标记 NEW_HIRE (不参与beta/alpha)
      5. 最后记录距今 > 6个月标记 INACTIVE
    """
    as_of = as_of or datetime.now()
    by_adv = {}
    for r in raw_rows:
        aid = str(r["advisor_id"])
        rev = round(float(r["revenue"] or 0), 2)
        if rev < 0:
            rev = 0.0  # 负数回款视为异常，先截断，插值阶段再修
        slot = by_adv.setdefault(aid, {
            "name": r.get("advisor_name") or aid,
            "quarters": {}, "flags": []})
        slot["quarters"][(int(r["year"]), int(r["quarter"]))] = rev

    cur_y, cur_q = as_of.year, (as_of.month - 1) // 3 + 1

    def q_index(yq):
        return yq[0] * 4 + yq[1]

    def from_index(i):
        return (i // 4, i % 4) if i % 4 != 0 else (i // 4 - 1, 4)

    result = {}
    for aid, slot in by_adv.items():
        qs = slot["quarters"]
        if not qs:
            continue
        idxs = sorted(q_index(k) for k in qs)
        first_i, last_i = idxs[0], idxs[-1]

        # 2. 补全缺失季度 = 0
        full = {}
        for i in range(first_i, min(last_i, q_index((cur_y, cur_q))) + 1):
            yq = from_index(i)
            full[yq] = round(qs.get(yq, 0.0), 2)

        # 1. 3sigma 异常值 -> 插值
        vals = list(full.values())
        n = len(vals)
        mean = sum(vals) / n
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / n) if n > 1 else 0
        keys = sorted(full.keys())
        outliers = []
        if sd > 0:
            for j, k in enumerate(keys):
                if full[k] > mean + 3 * sd:
                    prev_v = full[keys[j - 1]] if j > 0 else full[k]
                    next_v = full[keys[j + 1]] if j < n - 1 else full[k]
                    full[k] = round((prev_v + next_v) / 2, 2)
                    outliers.append(k)
        if outliers:
            slot["flags"].append(f"outlier_interp:{outliers}")

        # 4/5. 状态标记
        n_quarters = len(full)
        last_date = datetime(last_i // 4 if last_i % 4 else last_i // 4 - 1,
                             (last_i % 4 or 4) * 3, 28)
        status = "ACTIVE"
        if as_of - last_date > timedelta(days=183):
            status = "INACTIVE"
        if n_quarters < 2:
            status = "NEW_HIRE"

        result[aid] = {
            "name": slot["name"],
            "quarters": full,
            "status": status,
            "first_quarter": keys[0],
            "last_quarter": keys[-1],
            "n_quarters": n_quarters,
            "flags": slot["flags"],
        }
    return result


# ---------- 3.2 公司整体数据清洗 ----------

def clean_company_summary(raw_rows):
    """
    raw_rows: [{year, quarter, total_revenue(万), total_advisors, total_projects, win_rate?, ...}]
    返回: 按 (year,quarter) 排序的列表, 补全缺失季度(插值), 附加 qoq/yoy 增速
    """
    rows = {}
    for r in raw_rows:
        yq = (int(r["year"]), int(r["quarter"]))
        rows[yq] = {
            "year": yq[0], "quarter": yq[1],
            "total_revenue": round(float(r.get("total_revenue") or 0), 2),
            "total_advisors": int(r.get("total_advisors") or 0),
            "total_projects": int(r.get("total_projects") or 0),
            "win_rate": float(r["win_rate"]) if r.get("win_rate") is not None else None,
            "avg_fee_rate": float(r["avg_fee_rate"]) if r.get("avg_fee_rate") is not None else None,
            "avg_cycle_days": float(r["avg_cycle_days"]) if r.get("avg_cycle_days") is not None else None,
        }
    if not rows:
        return []

    def q_index(yq): return yq[0] * 4 + yq[1]
    def from_index(i): return (i // 4, i % 4) if i % 4 != 0 else (i // 4 - 1, 4)

    idxs = sorted(q_index(k) for k in rows)
    series = []
    for i in range(idxs[0], idxs[-1] + 1):
        yq = from_index(i)
        if yq in rows:
            series.append(rows[yq])
        else:
            # 缺失季度: 前后线性插值
            prev_r = rows.get(from_index(i - 1))
            next_r = rows.get(from_index(i + 1))
            interp = {k: (round((prev_r[k] + next_r[k]) / 2, 2) if prev_r and next_r
                          and isinstance(prev_r.get(k), (int, float)) else None)
                      for k in ["total_revenue", "total_advisors", "total_projects"]}
            series.append({"year": yq[0], "quarter": yq[1], "interpolated": True, **interp})

    # 环比 / 同比增速
    for j, s in enumerate(series):
        prev = series[j - 1] if j > 0 else None
        yoy = series[j - 4] if j >= 4 else None
        s["qoq"] = round((s["total_revenue"] - prev["total_revenue"]) / prev["total_revenue"], 4) \
            if prev and prev["total_revenue"] else None
        s["yoy"] = round((s["total_revenue"] - yoy["total_revenue"]) / yoy["total_revenue"], 4) \
            if yoy and yoy["total_revenue"] else None
    return series


# ---------- alpha 辅助: 客户来源占比 ----------

def compute_self_ratio(client_rows):
    """raw: [{advisor_id, source_type, total_revenue}] -> {advisor_id: self_revenue_ratio}"""
    agg = {}
    for r in client_rows:
        aid = str(r["advisor_id"])
        a = agg.setdefault(aid, {"self": 0.0, "total": 0.0})
        rev = float(r.get("total_revenue") or 0)
        a["total"] += rev
        if str(r.get("source_type", "")).upper() in ("SELF", "顾问开发"):
            a["self"] += rev
    return {aid: (a["self"] / a["total"] if a["total"] else 0.0) for aid, a in agg.items()}
