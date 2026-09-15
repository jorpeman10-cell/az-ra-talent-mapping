# -*- coding: utf-8 -*-
"""调参第二轮: 修正 alpha 重复计数 + mu 窗口变体
  v1: 文档原公式 (mu4, eb = mu*4*factor + alpha*4*(1-mcv*0.5))
  v4: mu4, 去掉alpha加法项
  v5: mu=max(mu4,mu8), 去掉alpha加法项
  v6: mu=近12Q中位数, 去掉alpha加法项
"""
import sys, os, json, math, statistics
sys.path.insert(0, r"C:/Users/EDY/Documents/kimi/workspace/headhunt_model")
from step3_cleaning import clean_quarterly_revenue, clean_company_summary, compute_self_ratio
from step4_engine import determine_market_phase, _linreg

CACHE = os.path.join(os.path.dirname(__file__), "raw_cache.json")
raw = json.load(open(CACHE, encoding="utf-8"))

advisors = clean_quarterly_revenue(raw["A"])
master = {str(a["advisor_id"]): a for a in raw["advisors"]}
company_full = clean_company_summary(raw["D"])
self_ratio = compute_self_ratio(raw["B"])


def beta_alpha(keys, hist, mu, company, sr):
    market_by_q = {(s["year"], s["quarter"]): s["total_revenue"] for s in company}
    ar, mr = [], []
    for i in range(1, len(keys)):
        pm, cm = market_by_q.get(keys[i - 1]), market_by_q.get(keys[i])
        if hist[i - 1] > 0 and pm:
            ar.append((hist[i] - hist[i - 1]) / hist[i - 1])
            mr.append((cm - pm) / pm)
    if len(ar) >= 6 and len(set(round(r, 6) for r in mr)) > 1:
        beta, _ = _linreg(mr, ar)
        alpha = mu * max(0.0, 1 - beta * (sum(mr) / len(mr)))
    else:
        beta, alpha = 1.0, mu * (sr if sr is not None else 0.2)
    return beta, alpha


def calc(hist, keys, company, sr, mu_mode, use_alpha_add):
    if mu_mode == "mu4":
        recent = hist[-4:]
        mu = sum(recent) / len(recent)
    elif mu_mode == "max48":
        r4, r8 = hist[-4:], hist[-8:] if len(hist) >= 8 else hist
        mu = max(sum(r4) / len(r4), sum(r8) / len(r8))
    elif mu_mode == "med12":
        r12 = hist[-12:]
        mu = statistics.median(r12)
    sd = math.sqrt(sum((x - mu) ** 2 for x in hist[-4:]) / len(hist[-4:]))
    cv = sd / mu if mu > 0 else 1.0
    beta, alpha = beta_alpha(keys, hist, mu, company, sr)
    return mu, cv, beta, alpha


def capacity(mu, cv, beta, alpha, market, use_alpha_add):
    slope, mcv = market["market_slope"], market["market_cv"]
    tf = 1 + slope * beta
    vp = mcv * cv * beta if mcv > 0.25 else 0.0
    eb = mu * 4 * max(0.0, tf - vp)
    if use_alpha_add:
        eb += alpha * 4 * (1 - mcv * 0.5)
    td = min(0.6, min(0.5, cv * 0.5) + mcv * 0.3)
    return eb * (1 - td)


VARIANTS = {
    "v1_doc":      ("mu4", True),
    "v4_noDup":    ("mu4", False),
    "v5_max48":    ("max48", False),
    "v6_med12":    ("med12", False),
}
results = {v: [] for v in VARIANTS}
rows = []

for aid, adv in advisors.items():
    if master.get(aid, {}).get("status") != "Active":
        continue
    qs = adv["quarters"]
    keys = sorted(qs.keys())
    if len(keys) < 9:
        continue
    tkeys = keys[:-4]
    train_hist = [qs[k] for k in tkeys]
    actual = sum(qs[k] for k in keys[-4:])
    if actual <= 0:
        continue
    comp_train = [s for s in company_full if (s["year"], s["quarter"]) <= tkeys[-1]]
    market = determine_market_phase(comp_train)
    row = {"name": adv["name"], "actual": round(actual, 1)}
    for vn, (mu_mode, use_add) in VARIANTS.items():
        mu, cv, beta, alpha = calc(train_hist, tkeys, comp_train, self_ratio.get(aid), mu_mode, use_add)
        pred = capacity(mu, cv, beta, alpha, market, use_add)
        results[vn].append(abs(pred - actual) / actual)
        row[vn] = round(pred, 1)
    rows.append(row)

hdr = f"{'顾问':<8}{'实际4Q':>8}" + "".join(f"{v:>10}" for v in VARIANTS)
print(hdr)
for r in rows:
    print(f"{r['name']:<8}{r['actual']:>8}" + "".join(f"{r[v]:>10}" for v in VARIANTS))
print()
for vn, apes in results.items():
    s = sorted(apes)
    print(f"{vn:<12} MAPE={sum(apes)/len(apes):.1%}  中位APE={s[len(s)//2]:.1%}  n={len(apes)}")
