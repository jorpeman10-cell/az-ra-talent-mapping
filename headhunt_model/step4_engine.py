# -*- coding: utf-8 -*-
"""
第四章 核心计算流程 + 第五章 输出规范
复用 headhunt_model_irr20.HeadhuntDecisionModel 的三模式测算/NPV/IRR,
在其上实现:
  Step1 calculate_advisor_profile()   四维度画像 (mu, CV, beta, alpha)
  Step2 determine_market_phase()      市场阶段判定
  Step3 calculate_effective_capacity() 市场-顾问交互
  Step4/5 接入 irr20 的 evaluate()    三模式 + 决策
输出: 单顾问决策JSON (5.1) + 批量排名 (5.2)
"""
import sys, math
sys.path.insert(0, r"C:/Users/EDY/Documents/kimi/workspace")
from headhunt_model_irr20 import HeadhuntDecisionModel


# ---------- Step 1: 顾问画像四维度 ----------

def get_last_n_quarters(quarters_dict, n=4):
    """quarters_dict: {(y,q): revenue} -> 最近n个季度的值(按时间序)"""
    keys = sorted(quarters_dict.keys())
    return [quarters_dict[k] for k in keys[-n:]]


def _linreg(xs, ys):
    """返回 (slope, intercept); xs=market_returns, ys=advisor_returns"""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    var = sum((x - mx) ** 2 for x in xs)
    if var < 1e-12:
        return 1.0, 0.0
    slope = cov / var
    return slope, my - slope * mx


def calculate_advisor_profile(aid, advisor_quarters, company_series, self_ratio=None):
    """
    advisor_quarters: {(y,q): revenue} 清洗后的季度序列
    company_series: clean_company_summary 输出 (含 year/quarter/total_revenue)
    self_ratio: 表B计算的独立获客占比 (用于 alpha 兜底)
    """
    keys = sorted(advisor_quarters.keys())
    history = [advisor_quarters[k] for k in keys]

    recent_4q = history[-4:] if len(history) >= 4 else history
    recent_8q = history[-8:] if len(history) >= 8 else history
    mu4 = sum(recent_4q) / len(recent_4q) if recent_4q else 0.0
    mu8 = sum(recent_8q) / len(recent_8q) if recent_8q else 0.0
    # v5 修正: mu 取 max(近4Q, 近8Q), 缓解趋势反转期低估 (回测 MAPE 83%->70%)
    mu = max(mu4, mu8)
    sd = math.sqrt(sum((x - mu) ** 2 for x in recent_4q) / len(recent_4q)) if recent_4q else 0.0
    cv = sd / mu if mu > 0 else 1.0

    # beta/alpha: 顾问环比 vs 公司环比 回归 (需 >= 6个收益率样本, 即 >= 7个季度)
    market_by_q = {(s["year"], s["quarter"]): s["total_revenue"] for s in company_series}
    adv_ret, mkt_ret = [], []
    for i in range(1, len(keys)):
        prev_m, cur_m = market_by_q.get(keys[i - 1]), market_by_q.get(keys[i])
        if history[i - 1] > 0 and prev_m:
            adv_ret.append((history[i] - history[i - 1]) / history[i - 1])
            mkt_ret.append((cur_m - prev_m) / prev_m)

    if len(adv_ret) >= 6 and len(set(round(r, 6) for r in mkt_ret)) > 1:
        beta, _intercept = _linreg(mkt_ret, adv_ret)
        # 回归解释力 R², 供 v5 beta 收缩使用
        mm = sum(mkt_ret) / len(mkt_ret)
        am = sum(adv_ret) / len(adv_ret)
        cov = sum((x - mm) * (y - am) for x, y in zip(mkt_ret, adv_ret))
        vx = sum((x - mm) ** 2 for x in mkt_ret)
        vy = sum((y - am) ** 2 for y in adv_ret)
        r2 = (cov * cov) / (vx * vy) if vx > 1e-12 and vy > 1e-12 else 0.0
        avg_mkt = sum(mkt_ret) / len(mkt_ret)
        alpha_amount = mu * max(0.0, 1 - beta * avg_mkt)
        beta_estimated = False
    else:
        beta = 1.0
        r2 = 0.0
        # 有客户来源数据时用 self_ratio, 否则默认20%独立产能
        alpha_amount = mu * (self_ratio if self_ratio is not None else 0.2)
        beta_estimated = True

    return {
        "advisor_id": aid, "mu": round(mu, 2), "cv": round(cv, 4),
        "beta": round(beta, 4), "beta_r2": round(r2, 4), "alpha": round(alpha_amount, 2),
        "beta_estimated": beta_estimated,
        "n_history_quarters": len(history),
    }


# ---------- Step 2: 市场阶段判定 ----------

def determine_market_phase(company_series, n=8):
    last = company_series[-n:] if len(company_series) >= n else company_series
    revs = [s["total_revenue"] for s in last]
    if len(revs) < 5:
        return {"phase": "UNKNOWN", "market_slope": 0.0, "market_cv": 0.0,
                "reason": f"公司历史季度不足({len(revs)}<5)"}

    yoys = []
    for i in range(4, len(revs)):
        if revs[i - 4] > 0:
            yoys.append((revs[i] - revs[i - 4]) / revs[i - 4])
    market_slope = sum(yoys[-2:]) / len(yoys[-2:]) if yoys else 0.0

    mu = sum(revs) / len(revs)
    sd = math.sqrt(sum((x - mu) ** 2 for x in revs) / len(revs))
    market_cv = sd / mu if mu > 0 else 1.0

    if market_cv > 0.25:
        phase = "VOLATILE"
    elif market_slope > 0.10:
        phase = "RISING"
    elif market_slope < -0.10:
        phase = "FALLING"
    else:
        phase = "FLAT"
    return {"phase": phase, "market_slope": round(market_slope, 4),
            "market_cv": round(market_cv, 4), "window_quarters": len(revs)}


# ---------- Step 3: 市场-顾问交互计算 ----------

def calculate_effective_capacity(profile, market_phase, pipeline=None, activity=None):
    mu, cv, beta, alpha = profile["mu"], profile["cv"], profile["beta"], profile["alpha"]
    slope, mcv = market_phase["market_slope"], market_phase["market_cv"]

    # v4 修正: CV 取 min(回款CV, 面试CV) —— 两个都是真实节奏的带噪代理,
    # 回款CV含4-5个月滞后噪音, 面试CV在小样本下偏噪, 取小避免双重虚高
    cv_rev = cv
    cv_eff = cv
    cv_source = "revenue"
    if activity and activity.get("itv_cv") is not None:
        if activity["itv_cv"] < cv:
            cv_eff = activity["itv_cv"]
            cv_source = "interview"
        itv_qoq = max(-1.0, min(1.0, activity.get("itv_qoq") or 0.0))
    else:
        itv_qoq = 0.0

    # v4.1: 撤销面试qoq前瞻项 —— 与管道项(近12月签约)职责重复,
    # 且面试→签约转化期顾问会被双重惩罚(卞少为案例)
    #
    # v5 修正(beta 双罚问题):
    #  1) beta 收缩: beta_adj = 1 + (beta-1)*R²  —— 回归解释力差则缩回标准型
    #  2) 波动惩罚摘掉 beta: mcv*CV —— 方向暴露已由趋势因子承担
    #  3) 趋势因子加 0.2 地板, 避免高beta在下行市场被清零(王慧案例)
    beta_r2 = profile.get("beta_r2", 0.0)
    beta_adj = 1 + (beta - 1) * beta_r2
    trend_factor = 1 + slope * beta_adj
    volatility_penalty = mcv * cv_eff if mcv > 0.25 else 0.0

    # v5 修正: 去掉 alpha*4 加法项 (mu 本身已含 alpha 产能, 加法重复计数导致高估)
    # alpha 仍保留在 profile 中用于独立获客力展示
    #
    # v3 修正: 回款滞后低估 -> 有效流水基数取
    #   max(mu*4, 近12月签约额 * 历史回款率)
    # 签约是先行指标, 回款滞后4-5个月, 对 ramp-up 顾问 mu 系统性偏低
    hist_base = mu * 4
    pipeline_base = 0.0
    if pipeline and pipeline.get("signed_12m_wan"):
        prob = pipeline.get("collection_prob", 0.9)
        pipeline_base = pipeline["signed_12m_wan"] * prob
    base_flow = max(hist_base, pipeline_base)
    effective_base = base_flow * max(0.2, trend_factor - volatility_penalty)

    personal_discount = min(0.5, cv_eff * 0.5)
    market_discount_adj = mcv * 0.3
    total_discount = min(0.6, personal_discount + market_discount_adj)

    conservative = effective_base * (1 - total_discount)
    return {
        "effective_base": round(effective_base, 2),
        "conservative": round(conservative, 2),
        "trend_factor": round(trend_factor, 4),
        "volatility_penalty": round(volatility_penalty, 4),
        "total_discount": round(total_discount, 4),
        "hist_base": round(hist_base, 2),
        "pipeline_base": round(pipeline_base, 2),
        "base_source": "pipeline" if pipeline_base > hist_base else "history",
        "cv_used": round(cv_eff, 4), "cv_revenue": round(cv_rev, 4), "cv_source": cv_source,
        "itv_qoq": round(itv_qoq, 4),
        "beta_raw": beta, "beta_adj": round(beta_adj, 4), "beta_r2": beta_r2,
    }


# ---------- Step 4/5: 三模式测算 (复用 irr20) + 决策包装 ----------

DEFAULT_CONFIG = {
    "discount_rate": 0.12, "attrition_rate": 0.10, "terminal_multiple": 0.5,
    "irr_threshold": 0.20,
    "demand_pct": 0.0,        # 市场需求增量% (外部数据, 默认0)
    "competition_pct": 0.0,   # 竞争挤压%
    "target_pct": 15.0,       # 目标利润率%
    "insurance_pct": 28.0,    # 五险一金雇主比例%
    "lift_pct": 10.0,         # 孵化模式产能提升%
    "op_cost_pct": 15.0,      # 孵化运营成本占回款%
    "equity_pct": 20.0,       # 公司占孵化主体股权%
    "support_cost": 5.0,      # 孵化支持成本 万/年
    "company_fixed_cost": 8.0,  # 分摊固定成本 万/年/人
    "management_cost": 5.0,   # 分摊管理成本 万/年/人
    "salary_annual": 18.0,    # 默认年薪(万), 有真实数据时覆盖
}


def evaluate_advisor(profile, capacity, market_phase, advisor_quarters_recent4,
                     history_records, current_year, difficulty_curve, config=None):
    """调用 irr20 引擎, 返回 5.1 格式决策"""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    model = HeadhuntDecisionModel(
        discount_rate=cfg["discount_rate"], attrition_rate=cfg["attrition_rate"],
        terminal_multiple=cfg["terminal_multiple"], irr_threshold=cfg["irr_threshold"])

    # irr20 以"近4季度均值*4*(1-discount)"为保守产能;
    # 这里用 v2 交互模型的 conservative 反推等效 quarters, 保持财务部分原样复用
    mu = profile["mu"]
    scale = (capacity["conservative"] / (mu * 4)) if mu > 0 else 0.0
    eq_quarters = [q * scale for q in advisor_quarters_recent4] if advisor_quarters_recent4 else [0, 0, 0, 0]

    r = model.evaluate(
        quarters=eq_quarters,
        demand_pct=cfg["demand_pct"], competition_pct=cfg["competition_pct"],
        target_pct=cfg["target_pct"], insurance_pct=cfg["insurance_pct"],
        salary_annual=cfg["salary_annual"], lift_pct=cfg["lift_pct"],
        op_cost_pct=cfg["op_cost_pct"], equity_pct=cfg["equity_pct"],
        support_cost=cfg["support_cost"], history_records=history_records,
        current_year=current_year, company_fixed_cost=cfg["company_fixed_cost"],
        management_cost=cfg["management_cost"], difficulty_curve=difficulty_curve,
        discount_override=0.0)  # 折减已在 calculate_effective_capacity 完成

    emp_margin_y1 = (r["emp_profit_series"][0] / r["forecast_series"][0]
                     if r["forecast_series"][0] else None)
    confidence = "HIGH" if (not profile["beta_estimated"] and profile["n_history_quarters"] >= 8) \
        else ("MEDIUM" if profile["n_history_quarters"] >= 4 else "LOW")

    return {
        "advisor_id": profile["advisor_id"],
        "profile": {k: profile[k] for k in ("mu", "cv", "beta", "alpha")},
        "market_phase": market_phase,
        "capacity": {k: capacity[k] for k in ("effective_base", "conservative", "total_discount")},
        "models": {
            "employ": {"npv_3y": round(r["emp_npv"], 2),
                       "irr": round(r["emp_irr"], 4) if r["emp_irr"] is not None else None,
                       "margin_y1": round(emp_margin_y1, 4) if emp_margin_y1 is not None else None,
                       "feasible": r["emp_feasible"]},
            "incubate": {"npv_3y": round(r["incubate_npv"], 2),
                         "irr": round(r["incubate_irr"], 4) if r["incubate_irr"] is not None else None,
                         "company_rate": cfg["equity_pct"] / 100,
                         "feasible": r["inc_feasible"]},
        },
        "decision": r["decision"],
        "confidence": confidence,
    }


# ---------- 5.2 批量排名 ----------

def rank_advisors(decisions, market_phase):
    """
    rank_score = conservative产能 * 决策系数 * 市场适配系数
    下降/波动市场惩罚高beta, 上升市场奖励高beta
    """
    phase = market_phase["phase"]
    decision_w = {"EMPLOY": 1.0, "INCUBATE": 0.7, "PASS": 0.2}
    rows = []
    for d in decisions:
        beta = d["profile"]["beta"]
        if phase in ("FALLING", "VOLATILE"):
            mkt_fit = 1 / (1 + max(0, beta - 1))      # 高beta在差市场减分
        elif phase == "RISING":
            mkt_fit = 1 + max(0, beta - 1) * 0.5      # 高beta在好市场加分
        else:
            mkt_fit = 1.0
        score = d["capacity"]["conservative"] * decision_w.get(d["decision"], 0.2) * mkt_fit
        rows.append({
            "advisor_id": d["advisor_id"], "name": d.get("advisor_name", d["advisor_id"]),
            "beta": beta, "conservative": d["capacity"]["conservative"],
            "decision": d["decision"], "rank_score": round(score, 2),
        })
    rows.sort(key=lambda x: -x["rank_score"])
    return {"market_phase": phase, "market_slope": market_phase["market_slope"],
            "market_cv": market_phase["market_cv"], "advisors": rows}
