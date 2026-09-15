# -*- coding: utf-8 -*-
"""解析 _outputs/salary_detail.csv -> {姓名: {salary_annual(万), insurance_pct(%)}}
月薪口径 = 月工资+职位工资+津贴; 五险一金用表内实际雇主部分
跳过: 汇总行(无姓名)、'A/B'合并行(归属不明)、重名行(保留第一条并告警)
"""
import csv

CSV_PATH = r"C:/Users/EDY/.kimi/_outputs/salary_detail.csv"


def _num(s):
    s = (s or "").strip().replace(",", "")
    if s in ("", "/"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_salary_map(path=CSV_PATH):
    m, skipped = {}, []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    for r in rows[2:]:  # 前两行是表头
        if len(r) < 6:
            continue
        name = r[1].strip()
        if not name:
            continue
        if "/" in name:
            skipped.append(f"{name}(合并行)")
            continue
        base = _num(r[2]) + _num(r[3]) + _num(r[4])   # 月工资+职位工资+津贴
        ins = _num(r[5])                              # 五险一金(雇主)
        if base <= 0:
            continue
        if name in m:
            skipped.append(f"{name}(重名, 保留首条)")
            continue
        m[name] = {
            "base_monthly": base,
            "ins_monthly": ins,
            "salary_annual": round(base * 12 / 10000, 2),        # 万/年
            "insurance_pct": round(ins / base * 100, 1),         # %
        }
    return m, skipped


if __name__ == "__main__":
    m, skipped = load_salary_map()
    for name, v in m.items():
        print(f"{name:<8} 月薪{v['base_monthly']:>8.0f}  五险一金/月{v['ins_monthly']:>7.0f}"
              f"  年薪{v['salary_annual']:>6.2f}万  社保率{v['insurance_pct']:>5.1f}%")
    print("跳过:", skipped)
