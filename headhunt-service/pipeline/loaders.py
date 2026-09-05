# -*- coding: utf-8 -*-
"""外部数据加载: 底薪表(salary csv) + 成本拆分表(xlsx)
输出姓名键控字典, 路径由 config 注入
"""
import csv
import openpyxl


def _num(s):
    s = str(s or "").strip().replace(",", "")
    if s in ("", "/", "None"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_salary_map(path, departed_names=frozenset(), salary_overrides=None):
    """底薪口径 = 月工资+职位工资+津贴; 五险一金列为参考(成本xlsx优先)

    重名规则（2026-09-04 Steven 确认）：
    - 同一人多条（如魏菲 临床→市场 调任产生两条）→ 保留最后一条（财务表按时间追加）
    - 合并行 "A/B"：A 离职时归属留存者（如 沈铭骋/曹迎奥 → 曹迎奥）；
      留存者已有独立行则跳过合并行（如 刘科利/李彩霞，李彩霞有 14100 独立行）
    departed_names: 已离职名单，合并行中这些名字不计入归属
    salary_overrides: {姓名: 月薪总额(元)} 人工校准，覆盖表内数值
      （财务表滞后/录入错误时使用，如魏菲市场部实际 7000+2000=9000）
    """
    overrides = salary_overrides or {}
    m, skipped = {}, []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    # 合并行只在其留存者没有独立行时才归属（否则合并行是两人合计的旧记录）
    standalone_names = {
        r[1].strip() for r in rows[2:]
        if len(r) >= 6 and r[1].strip() and "/" not in r[1]
    }
    for r in rows[2:]:
        if len(r) < 6:
            continue
        name = r[1].strip()
        if not name:
            continue
        if "/" in name:
            survivors = [n.strip() for n in name.split("/")
                         if n.strip() and n.strip() not in departed_names]
            if len(survivors) == 1 and survivors[0] not in standalone_names:
                name = survivors[0]  # 合并行归属留存者
            else:
                skipped.append(f"{name}(合并行)")
                continue
        base = _num(r[2]) + _num(r[3]) + _num(r[4])
        if base <= 0:
            continue
        if name in m:
            # 同名多条 = 同一人调任/调薪的历史记录，财务表按时间追加，取最新（最后一条）
            m[name] = {"base_monthly": base,
                       "salary_annual": round(base * 12 / 10000, 2)}
            continue
        m[name] = {"base_monthly": base,
                   "salary_annual": round(base * 12 / 10000, 2)}
    for name, monthly in overrides.items():
        monthly = float(monthly)
        if monthly > 0:
            m[name] = {"base_monthly": monthly,
                       "salary_annual": round(monthly * 12 / 10000, 2)}
    return m, skipped


def load_cost_map(path, overhead_mode="per_head", months=7,
                  departed_names=frozenset()):
    """xlsx 人员累计汇总: 社保率实算 + 公共管理费用分摊年化(默认按人头均摊)

    同名多条取最后一条（调任/调薪取最新）；合并行 "A/B" 在 departed_names
    里的名字不计，归属留存者（留存者已有独立行则跳过）。
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["人员累计汇总"]
    all_rows = list(ws.iter_rows(min_row=2, values_only=True))
    # 先扫独立行名单：合并行只在其留存者没有独立行时才归属（合并行是两人合计，
    # 覆盖独立行会把社保率算错）
    standalone_names = {
        str(row[2]).strip() for row in all_rows
        if row and row[2] and "/" not in str(row[2])
    }
    rows, skipped = [], {}
    for row in all_rows:
        if not row or not row[2]:
            continue
        name = str(row[2]).strip()
        if "/" in name:
            survivors = [n.strip() for n in name.split("/")
                         if n.strip() and n.strip() not in departed_names]
            if len(survivors) != 1 or survivors[0] in standalone_names:
                skipped[name] = "合并行"
                continue
            name = survivors[0]
        if float(row[3] or 0) <= 0:
            continue
        rows.append({
            "name": name, "salary": float(row[3] or 0),
            "social": float(row[4] or 0), "fund": float(row[5] or 0),
            "overhead_7m": float(row[8] or 0), "total_7m": float(row[9] or 0),
        })
    per_head_7m = sum(r["overhead_7m"] for r in rows) / len(rows) if rows else 0.0
    m = {}
    for r in rows:
        name = r["name"]
        oh = per_head_7m if overhead_mode == "per_head" else r["overhead_7m"]
        m[name] = {
            "insurance_pct": round((r["social"] + r["fund"]) / r["salary"] * 100, 1),
            "overhead_annual_wan": round(oh / months * 12 / 10000, 2),
            "total_cost_annual_wan": round(r["total_7m"] / months * 12 / 10000, 2),
        }
    return m, skipped
