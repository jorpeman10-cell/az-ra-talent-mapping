# -*- coding: utf-8 -*-
"""验证: 对3名真实顾问做留出回测 —— 用 T-4 之前的数据预测最近4季度合计回款, 对比实际"""
import sys
sys.path.insert(0, r"C:/Users/EDY/Documents/kimi/workspace/headhunt_model")
from step2_collect import collect_all
from step3_cleaning import clean_quarterly_revenue, clean_company_summary, compute_self_ratio
from step4_engine import calculate_advisor_profile, determine_market_phase, calculate_effective_capacity

TARGETS = ["933", "946", "927"]  # 王嘉裕 / 赵婉玉 / 卞少为 (ACTIVE排名前3)

raw = collect_all()
advisors = clean_quarterly_revenue(raw["A"])
company_full = clean_company_summary(raw["D"])
self_ratio = compute_self_ratio(raw["B"])

print(f"{'顾问':<8}{'预测4Q合计':>10}{'实际4Q合计':>10}{'APE':>8}  说明")
apes = []
for aid in TARGETS:
    adv = advisors[aid]
    qs = adv["quarters"]
    keys = sorted(qs.keys())
    train_keys, test_keys = keys[:-4], keys[-4:]
    train_q = {k: qs[k] for k in train_keys}
    actual_4q = sum(qs[k] for k in test_keys)

    # 市场阶段用训练窗口内的公司序列 (避免未来数据泄露)
    cut = train_keys[-1]
    comp_train = [s for s in company_full
                  if (s["year"], s["quarter"]) <= cut]
    market = determine_market_phase(comp_train)
    profile = calculate_advisor_profile(aid, train_q, comp_train,
                                        self_ratio=self_ratio.get(aid))
    cap = calculate_effective_capacity(profile, market)
    pred_4q = cap["conservative"]

    ape = abs(pred_4q - actual_4q) / actual_4q if actual_4q else float("nan")
    apes.append(ape)
    print(f"{adv['name']:<8}{pred_4q:>10.1f}{actual_4q:>10.1f}{ape:>8.1%}  "
          f"训练{len(train_keys)}Q beta={profile['beta']:.2f} 市场={market['phase']}")
    print(f"  训练季度: {[(k, qs[k]) for k in train_keys[-6:]]}")
    print(f"  测试季度: {[(k, qs[k]) for k in test_keys]}")

print(f"\nMAPE(3人) = {sum(apes)/len(apes):.1%}")
