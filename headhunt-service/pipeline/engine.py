# -*- coding: utf-8 -*-
"""核心计算: 画像四维度 / 市场阶段 / 市场-顾问交互 / 三模式决策包装 / 批量排名
口径历经8轮真实数据修正, 公式注释保留版本沿革
"""
import math
from datetime import datetime

from .finance import HeadhuntDecisionModel


# ---------- Step 1: 顾问画像四维度 ----------

def get_last_n_quarters(quarters_dict, n=4):
    keys = sorted(quarters_dict.keys())
    return [quarters_dict[k] for k in keys[-n:]]


def _linreg(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    var = sum((x - mx) ** 2 for x in xs)
    if var < 1e-12:
        return 1.0, 0.0
    slope = cov / var
    return slope, my - slope * mx


def calculate_advisor_profile(aid, advisor_quarters, company_series, self_ratio=None):
    keys = sorted(advisor_quarters.keys())
    history = [advisor_quarters[k] for k in keys]

    recent_4q = history[-4:] if len(history) >= 4 else history
    recent_8q = history[-8:] if len(history) >= 8 else history
    mu4 = sum(recent_4q) / len(recent_4q) if recent_4q else 0.0
    mu8 = sum(recent_8q) / len(recent_8q) if recent_8q else 0.0
    # mu 取 max(近4Q, 近8Q), 缓解趋势反转期低估 (回测 MAPE 83%->70%)
    mu = max(mu4, mu8)
    sd = math.sqrt(sum((x - mu) ** 2 for x in recent_4q) / len(recent_4q)) if recent_4q else 0.0
    cv = sd / mu if mu > 0 else 1.0

    # beta/alpha: 顾问环比 vs 公司环比 回归 (需 >= 6个收益率样本)
    market_by_q = {(s["year"], s["quarter"]): s["total_revenue"] for s in company_series}
    adv_ret, mkt_ret = [], []
    for i in range(1, len(keys)):
        prev_m, cur_m = market_by_q.get(keys[i - 1]), market_by_q.get(keys[i])
        if history[i - 1] > 0 and prev_m:
            adv_ret.append((history[i] - history[i - 1]) / history[i - 1])
            mkt_ret.append((cur_m - prev_m) / prev_m)

    if len(adv_ret) >= 6 and len(set(round(r, 6) for r in mkt_ret)) > 1:
        beta, _ = _linreg(mkt_ret, adv_ret)
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
        beta, r2 = 1.0, 0.0
        alpha_amount = mu * (self_ratio if self_ratio is not None else 0.2)
        beta_estimated = True

    return {
        "advisor_id": aid, "mu": round(mu, 2), "cv": round(cv, 4),
        "beta": round(beta, 4), "beta_r2": round(r2, 4), "alpha": round(alpha_amount, 2),
        "beta_estimated": beta_estimated,
        "n_history_quarters": len(history),
    }


# ---------- Step 2: 市场阶段判定 ----------

def determine_market_phase(company_series, n=8, external_slope=None):
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
    slope_source = "company"

    # 外部行业口径覆盖 (医药行业猎头赛道, 季度维护; 配置 external_slope)
    if external_slope is not None:
        market_slope = external_slope
        slope_source = "external"

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
            "market_cv": round(market_cv, 4), "window_quarters": len(revs),
            "slope_source": slope_source}


# ---------- Step 3: 市场-顾问交互计算 ----------

def calculate_effective_capacity(profile, market_phase, pipeline=None, activity=None,
                                 deals_12m=None, client_series=None, risk=None):
    """三层风险结构（2026-09-05 实证改造，docs/2026-09-05-三层风险结构-引擎改造方案.md）：
    L1 CV 先验收缩（M/活动量结构先验 + 实际 CV 按样本量混合）
    L2 客户流失监测（连续 2 季活跃客户数下降 → 折减加点，只加不减）
    L3 分位情景（回款序列分位年化，数据驱动；新人通道用 CV 先验展开）
    """
    risk = risk or {}
    cvp = risk.get("cv_prior", {})
    A = float(cvp.get("a", 1.6716))
    B1 = float(cvp.get("b1", -0.4454))
    B2 = float(cvp.get("b2", 0.3667))
    K = float(cvp.get("k", 8))
    CLIP = (float(cvp.get("clip_min", 0.1)), float(cvp.get("clip_max", 2.5)))
    CHURN_ADDON = float(risk.get("churn_addon_pp", 5)) / 100.0

    mu, cv, beta, alpha = profile["mu"], profile["cv"], profile["beta"], profile["alpha"]
    slope, mcv = market_phase["market_slope"], market_phase["market_cv"]
    n_hist = profile.get("n_history_quarters", 0)

    # CV 取 min(回款CV, 面试CV): 回款CV含4-5个月滞后噪音, 面试CV小样本偏噪, 取小
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

    # ---- L1: CV 先验收缩 ----
    # 先验 = a + b1·ln(M) + b2·推荐量季CV（实证: M 单量多波动低, 活动忽高忽低波动大）
    cv_prior = None
    m_deals = float(deals_12m or 0)
    rec_cv = (activity or {}).get("rec_cv")
    if m_deals > 0:
        raw_prior = A + B1 * math.log(m_deals) + B2 * float(rec_cv or 0.0)
        cv_prior = round(min(CLIP[1], max(CLIP[0], raw_prior)), 4)
    # 无先验输入（无成单）时保持原口径
    if cv_prior is None or risk.get("enabled") is False:
        cv_shrunk = cv_eff
    elif n_hist == 0:
        cv_shrunk = cv_prior  # 新人通道: 纯先验（实际 CV 无样本, 哨兵值不算测量值）
    elif cv_eff <= cv_prior:
        # 单侧收缩: 实际低波动有实证支撑(且系 min(回款,面试) 精选口径), 不上拉;
        # 先验只用于压制高噪音端
        cv_shrunk = cv_eff
    else:
        cv_shrunk = round((K / (n_hist + K)) * cv_prior + (n_hist / (n_hist + K)) * cv_eff, 4)

    # beta 修正: 1) 收缩 beta_adj = 1+(beta-1)*R²  2) 波动惩罚摘 beta  3) 趋势因子 0.2 地板
    beta_r2 = profile.get("beta_r2", 0.0)
    beta_adj = 1 + (beta - 1) * beta_r2
    trend_factor = 1 + slope * beta_adj
    volatility_penalty = mcv * cv_shrunk if mcv > 0.25 else 0.0

    # 有效流水基数 = max(mu*4, 近12月签约额*历史回款率): 签约是先行指标,
    # 回款滞后4-5个月, 对 ramp-up 顾问 mu 系统性偏低
    hist_base = mu * 4
    pipeline_base = 0.0
    if pipeline and pipeline.get("signed_12m_wan"):
        prob = pipeline.get("collection_prob", 0.9)
        pipeline_base = pipeline["signed_12m_wan"] * prob
    base_flow = max(hist_base, pipeline_base)
    effective_base = base_flow * max(0.2, trend_factor - volatility_penalty)

    personal_discount = min(0.5, cv_shrunk * 0.5)
    market_discount_adj = mcv * 0.3
    total_discount = min(0.6, personal_discount + market_discount_adj)

    # ---- L2: 客户流失监测（连续 2 季活跃客户数下降 → 折减加点）----
    # 只看已完结季度: 当季未完结时客户数必然偏低, 会造成假性流失
    churn_alert = False
    client_delta_2q = None
    if client_series:
        cur_y, cur_q = datetime.now().year, (datetime.now().month - 1) // 3 + 1
        keys = [k for k in sorted(client_series.keys()) if k < (cur_y, cur_q)]
        if len(keys) >= 3:
            d1 = client_series[keys[-2]] - client_series[keys[-3]]
            d2 = client_series[keys[-1]] - client_series[keys[-2]]
            client_delta_2q = d1 + d2
            churn_alert = d1 < 0 and d2 < 0
    if churn_alert and risk.get("enabled") is not False:
        total_discount = min(0.6, total_discount + CHURN_ADDON)

    conservative = effective_base * (1 - total_discount)

    # ---- L3: 分位情景（数据驱动：回款序列分位年化；新人通道用 CV 先验展开）----
    spread = min(0.6, max(0.15, cv_shrunk / 2))
    quantiles = {
        "p25": round(conservative * (1 - spread), 2),
        "p50": round(conservative, 2),
        "p75": round(conservative * (1 + spread), 2),
    }
    return {
        "effective_base": round(effective_base, 2),
        "conservative": round(conservative, 2),
        "trend_factor": round(trend_factor, 4),
        "volatility_penalty": round(volatility_penalty, 4),
        "total_discount": round(total_discount, 4),
        "hist_base": round(hist_base, 2),
        "pipeline_base": round(pipeline_base, 2),
        "base_source": "pipeline" if pipeline_base > hist_base else "history",
        "cv_used": round(cv_shrunk, 4), "cv_revenue": round(cv_rev, 4), "cv_source": cv_source,
        "cv_prior": cv_prior,
        "itv_qoq": round(itv_qoq, 4),
        "beta_raw": beta, "beta_adj": round(beta_adj, 4), "beta_r2": beta_r2,
        "quantiles": quantiles,
        "monitoring": {"client_delta_2q": client_delta_2q, "churn_alert": churn_alert},
    }


# ---------- Step 4/5: 三模式测算 + 决策包装 ----------

def make_model(cfg):
    return HeadhuntDecisionModel(
        discount_rate=cfg["discount_rate"], attrition_rate=cfg["attrition_rate"],
        terminal_multiple=cfg["terminal_multiple"], irr_threshold=cfg["irr_threshold"],
        tiers=[(float(c), float(r)) for c, r in cfg["commission_tiers"]],
        tax_ratio=cfg["tax_ratio"])


def evaluate_advisor(profile, capacity, market_phase, advisor_quarters_recent4,
                     history_records, current_year, difficulty_curve, cfg):
    """cfg 为 config.yaml 展开后的扁平 dict"""
    model = make_model(cfg)

    # 财务引擎以"近4季度均值*4"为产能基数; 用交互模型的 conservative 反推等效 quarters
    mu = profile["mu"]
    scale = (capacity["conservative"] / (mu * 4)) if mu > 0 else 0.0
    if advisor_quarters_recent4:
        eq_quarters = [q * scale for q in advisor_quarters_recent4]
    elif capacity["conservative"] > 0:
        # 新人通道: 无回款历史, 用管道口径的保守产能摊 4 个季度喂给财务引擎
        eq_quarters = [capacity["conservative"] / 4] * 4
    else:
        eq_quarters = [0, 0, 0, 0]

    def _run(eq):
        return model.evaluate(
            quarters=eq,
            demand_pct=cfg["demand_pct"], competition_pct=cfg["competition_pct"],
            target_pct=cfg["target_pct"], insurance_pct=cfg["insurance_pct"],
            salary_annual=cfg["salary_annual"], lift_pct=cfg["lift_pct"],
            op_cost_pct=cfg["op_cost_pct"], equity_pct=cfg["equity_pct"],
            support_cost=cfg["support_cost"], history_records=history_records,
            current_year=current_year, company_fixed_cost=cfg["company_fixed_cost"],
            management_cost=cfg["management_cost"], difficulty_curve=difficulty_curve,
            discount_override=0.0)  # 折减已在 calculate_effective_capacity 完成

    r = _run(eq_quarters)

    # ---- L3: 分位情景 —— 每个产能分位各跑一遍财务引擎 ----
    quantile_models = {}
    cons = capacity.get("conservative") or 0.0
    for qk, cq in (capacity.get("quantiles") or {}).items():
        if cons > 0 and advisor_quarters_recent4:
            eq_q = [x * (cq / cons) for x in eq_quarters]
        elif cons > 0:
            eq_q = [cq / 4] * 4
        else:
            eq_q = [0, 0, 0, 0]
        rq = _run(eq_q)
        quantile_models[qk] = {
            "npv_3y": round(rq["emp_npv"], 2),
            "irr": round(rq["emp_irr"], 4) if rq["emp_irr"] is not None else None,
            "margin_y1": round(rq["emp_margin_y1"], 4),
            "feasible": rq["emp_feasible"],
            "decision": rq["decision"],
        }

    confidence = "HIGH" if (not profile["beta_estimated"] and profile["n_history_quarters"] >= 8) \
        else ("MEDIUM" if profile["n_history_quarters"] >= 4 else "LOW")

    return {
        "advisor_id": profile["advisor_id"],
        "profile": {k: profile[k] for k in ("mu", "cv", "beta", "alpha")},
        "market_phase": market_phase,
        "capacity": {k: capacity[k] for k in ("effective_base", "conservative", "total_discount",
                                              "quantiles", "monitoring", "cv_prior")
                     if k in capacity},
        "models": {
            "employ": {"npv_3y": round(r["emp_npv"], 2),
                       "irr": round(r["emp_irr"], 4) if r["emp_irr"] is not None else None,
                       "margin_y1": round(r["emp_margin_y1"], 4),
                       "feasible": r["emp_feasible"]},
            "incubate": {"npv_3y": round(r["incubate_npv"], 2),
                         "irr": round(r["incubate_irr"], 4) if r["incubate_irr"] is not None else None,
                         "company_rate": cfg["equity_pct"] / 100,
                         "feasible": r["inc_feasible"]},
            "quantiles": quantile_models,
        },
        "decision": r["decision"],
        "decision_band": {
            "p50_base": r["decision"],
            "p25_bear": (quantile_models.get("p25") or {}).get("decision"),
            "p75_bull": (quantile_models.get("p75") or {}).get("decision"),
        },
        "confidence": confidence,
    }


# ---------- 批量排名 ----------

def rank_advisors(decisions, market_phase):
    phase = market_phase["phase"]
    decision_w = {"EMPLOY": 1.0, "INCUBATE": 0.7, "PASS": 0.2}
    rows = []
    for d in decisions:
        beta = d["profile"]["beta"]
        if phase in ("FALLING", "VOLATILE"):
            mkt_fit = 1 / (1 + max(0, beta - 1))
        elif phase == "RISING":
            mkt_fit = 1 + max(0, beta - 1) * 0.5
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
            "market_cv": market_phase["market_cv"],
            "slope_source": market_phase.get("slope_source", "company"),
            "advisors": rows}
