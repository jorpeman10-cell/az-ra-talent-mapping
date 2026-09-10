# -*- coding: utf-8 -*-
"""确定性判断依据生成器: 把决策 JSON 转成 Agent/HR 可直接引用的中文依据文本
所有内容来自已计算字段, 无 LLM, 无推测
"""


def build_rationale(d: dict) -> str:
    p, c, m = d["profile"], d["capacity"], d["models"]
    mp = d["market_phase"]
    lines = [
        f"【{d['advisor_name']} 决策: {d['decision']}】(置信度 {d['confidence']})",
        "",
    ]
    if d.get("new_hire_channel"):
        lines.append(
            "⚠️ 新人通道: 该顾问无回款历史(入职以来无业绩产出/调任), "
            "产能完全基于在途签约管道估算, 置信度 LOW, 结果仅供观察期参考。")
    monitoring = c.get("monitoring") or {}
    if monitoring.get("churn_alert"):
        lines.append(
            f"⚠️ 客户流失预警: 活跃客户数连续 2 季下降"
            f"(Δ2季={monitoring.get('client_delta_2q')}), 折减已加厚 5pp。")
    quantiles = c.get("quantiles") or {}
    if quantiles:
        lines.append(
            f"   三档情景: 悲观档产能 {quantiles.get('p25')}万 / 基准档 {quantiles.get('p50')}万 "
            f"/ 乐观档 {quantiles.get('p75')}万（收缩后 CV={c.get('cv_used')}，先验 {c.get('cv_prior')}）。")
    lines += [
        f"1. 产能: 季度中枢 μ={p['mu']}万, 波动率 CV={c.get('cv_used', p['cv'])}"
        f"({'面试口径' if c.get('cv_source') == 'interview' else '回款口径'}), "
        f"市场敏感度β={p['beta']}(收缩后{c.get('beta_adj', 1)}), 独立获客α={p['alpha']}万/季。",
        f"2. 市场: {mp['phase']} 阶段, 斜率{mp['market_slope']:+.1%}"
        f"({'外部行业口径' if mp.get('slope_source') == 'external' else '公司内部口径'}), "
        f"波动率{mp['market_cv']:.1%}。",
        f"3. 折减后保守产能 {c['conservative']}万/年 (有效基数{c['effective_base']}万 × "
        f"(1-总折减{c['total_discount']:.0%}))。",
    ]
    if d.get("pipeline"):
        pl = d["pipeline"]
        lines.append(
            f"   其中在途签约接管基数: 近12月签约{pl['signed_12m_wan']}万 × 历史回款率"
            f"{pl['collection_prob']:.0%} = {pl['pipeline_base']}万"
            f"({'签约口径高于回款口径, 取大' if pl['base_source'] == 'pipeline' else '回款口径更高'})。")
    lines += [
        f"4. 成本: 年薪{d['salary_annual']}万 + 社保{d['insurance_pct']}% + 公摊{d['overhead_annual']}万/年"
        f"(来源: {d.get('cost_source', 'default')})。",
        f"5. 雇员模式: 首年利润率{m['employ']['margin_y1']:.1%}(门槛15%), "
        f"3年NPV {m['employ']['npv_3y']}万, "
        f"IRR {'无解(现金流全负)' if m['employ']['irr'] is None else format(m['employ']['irr'], '.0%')}"
        f"(门槛20%) → {'可行' if m['employ']['feasible'] else '不可行'}。",
        f"6. 孵化模式: 3年NPV {m['incubate']['npv_3y']}万, "
        f"IRR {'无解' if m['incubate']['irr'] is None else format(m['incubate']['irr'], '.0%')} "
        f"→ {'可行' if m['incubate']['feasible'] else '不可行'}。",
    ]
    if d["decision"] == "PASS":
        lines.append("结论: 两种模式均不满足财务门槛, 建议 PASS 或转为观察(连续2季回款达标再评估)。")
    elif d["decision"] == "INCUBATE":
        lines.append("结论: 雇员模式利润率/IRR不达标但孵化模式可行, 建议转合伙孵化。")
    else:
        lines.append("结论: 雇员模式满足利润率与IRR双门槛, 建议维持/加码雇佣。")
    return "\n".join(lines)


def build_scan_rationale(s: dict) -> str:
    lim = f"{s['employ_limit_monthly']}元/月" if s["employ_limit_monthly"] else "当前区间无 EMPLOY 空间"
    be = f"{s['breakeven_monthly']}元/月" if s["breakeven_monthly"] else "—"
    return (
        f"【{s['advisor_name']} 调薪扫描 · 情景{s['scenario']}】\n"
        f"产能口径: 保守产能 {s['capacity_conservative']}万/年 (斜率{s['slope_used']:+.2f})。\n"
        f"当前年薪 {s['current_salary_annual']}万。\n"
        f"EMPLOY 极限(满足15%利润率+20%IRR双门槛): {lim}; 盈亏平衡(NPV=0): {be}。\n"
        f"判断依据: 在极限月薪以内, 成本增速低于保守产能对应的毛利; 超出后首年利润率跌破15%门槛。"
        f"注: 该顾问提成盘子 {'未吃满(底薪>提成额), 加薪为纯固定成本增加' if s['current_salary_annual'] else ''}。")
