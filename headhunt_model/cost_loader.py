# -*- coding: utf-8 -*-
"""解析 2026年成本拆分结果_含社保公积金权重.xlsx -> 每人真实成本画像
输出: {姓名: {insurance_pct, overhead_annual_wan, total_cost_7m_wan, source}}
口径:
  insurance_pct = (社保+公积金)/工资 * 100
  overhead_annual_wan = 公共管理费用分摊 / 7 * 12 / 10000  (真实管理公摊年化, 万)
跳过: 合并行(A/B)、重名(魏菲x2, 保守不用)
"""
import openpyxl

XLSX_PATH = r"C:/Users/EDY/Desktop/数据库1/2026年成本拆分结果_含社保公积金权重.xlsx"
MONTHS = 7


def load_cost_map(path=XLSX_PATH, overhead_mode="per_head"):
    """overhead_mode: 'per_head' 按人头均摊(默认) / 'weight' 按工资权重分摊(xlsx原口径)"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["人员累计汇总"]
    rows, skipped = [], {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[2]:
            continue
        name = str(row[2]).strip()
        if "/" in name:
            skipped[name] = "合并行"
            continue
        if float(row[3] or 0) <= 0:
            continue
        rows.append({
            "name": name,
            "salary": float(row[3] or 0), "social": float(row[4] or 0),
            "fund": float(row[5] or 0),
            "overhead_7m": float(row[8] or 0), "total_7m": float(row[9] or 0),
        })
    # 按人头: 全员公共管理费用合计 / 有效人数
    per_head_7m = sum(r["overhead_7m"] for r in rows) / len(rows) if rows else 0.0

    m = {}
    for r in rows:
        name = r["name"]
        if name in m:
            skipped[name] = "重名, 不采用"
            m.pop(name, None)
            continue
        oh_7m = per_head_7m if overhead_mode == "per_head" else r["overhead_7m"]
        m[name] = {
            "insurance_pct": round((r["social"] + r["fund"]) / r["salary"] * 100, 1),
            "overhead_annual_wan": round(oh_7m / MONTHS * 12 / 10000, 2),
            "overhead_weight_annual_wan": round(r["overhead_7m"] / MONTHS * 12 / 10000, 2),
            "total_cost_annual_wan": round(r["total_7m"] / MONTHS * 12 / 10000, 2),
            "source": f"xlsx_2026成本拆分({overhead_mode})",
        }
    return m, skipped


if __name__ == "__main__":
    for mode in ("per_head", "weight"):
        m, skipped = load_cost_map(overhead_mode=mode)
        print(f"===== overhead_mode={mode} =====")
        print(f"{'姓名':<10}{'社保率%':>8}{'公摊年化(万)':>12}{'总成本年化(万)':>14}")
        for name, v in m.items():
            print(f"{name:<10}{v['insurance_pct']:>8}{v['overhead_annual_wan']:>12}{v['total_cost_annual_wan']:>14}")
        print("跳过:", skipped)
    # 校验: weight 模式与手工核算一致
    mw, _ = load_cost_map(overhead_mode="weight")
    assert abs(mw["于肖肖"]["overhead_annual_wan"] - 3.26) < 0.05, mw["于肖肖"]
    assert abs(mw["卞少为"]["overhead_annual_wan"] - 30.74) < 0.05, mw["卞少为"]
    print("校验通过: weight 模式与手工核算一致")
