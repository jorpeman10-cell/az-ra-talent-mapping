# -*- coding: utf-8 -*-
"""调参实验: 全部ACTIVE顾问留出回测, 对比3个变体的MAPE
  v1: 文档原公式 (mu=近4Q)
  v2: mu 窗口扩大到近8Q (平滑趋势反转)
  v3: v2 + alpha 上限 0.5*mu (防止与mu重复计算)
"""
import sys, os, json, math
sys.path.insert(0, r"C:/Users/EDY/Documents/kimi/workspace/headhunt_model")
from step3_cleaning import clean_quarterly_revenue, clean_company_summary, compute_self_ratio
from step4_engine import determine_market_phase, _linreg

CACHE = os.path.join(os.path.dirname(__file__), "raw_cache.json")

if os.path.exists(CACHE):
    raw = json.load(open(CACHE, encoding="utf-8"))
else:
    from step2_collect import collect_all
    raw = collect_all()
    # tuple keys 不便序列化, 直接存原始list即可
    json.dump(raw, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, default=str)

advisors = clean_quarterly_revenue(raw["A"])
master = {str(a["advisor_id"]): a for a in raw["advisors"]}
company_full = clean_company_summary(raw["D"])
self_ratio = compute_self_ratio(raw["B"])


def profile_variant(quarters, company, sr, mu_window, alpha_cap):
    keys = sorted(quarters.keys())
    hist = [quarters[k] for k in keys]
    recent = hist[-mu_window:] if len(hist) >= mu_window else hist
    mu = sum(recent) / len(recent)
    sd = math.sqrt(sum((x - mu) ** 2 for x in recent) / len(recent))
    cv = sd / mu if mu > 0 else 1.0
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
    if alpha_cap is not None:
        alpha = min(alpha, alpha_cap * mu)
    return mu, cv, beta, alpha


def capacity(mu, cv, beta, alpha, market):
    slope, mcv = market["market_slope"], market["market_cv"]
    tf = 1 + slope * beta
    vp = mcv * cv * beta if mcv > 0.25 else 0.0
    eb = mu * 4 * max(0.0, tf - vp) + alpha * 4 * (1 - mcv * 0.5)
    td = min(0.6, min(0.5, cv * 0.5) + mcv * 0.3)
    return eb * (1 - td)


VARIANTS = {"v1_doc(mu4)": (4, None), "v2_mu8": (8, None), "v3_mu8_alphaCap": (8, 0.5)}
results = {v: [] for v in VARIANTS}
detail = []

for aid, adv in advisors.items():
    if master.get(aid, {}).get("status") != "Active":
        continue
    qs = adv["quarters"]
    keys = sorted(qs.keys())
    if len(keys) < 9:
        continue
    train = {k: qs[k] for k in keys[:-4]}
    actual = sum(qs[k] for k in keys[-4:])
    if actual <= 0:
        continue
    comp_train = [s for s in company_full if (s["year"], s["quarter"]) <= keys[-5]]
    market = determine_market_phase(comp_train)
    row = {"name": adv["name"], "actual": round(actual, 1)}
    for vn, (win, cap) in VARIANTS.items():
        mu, cv, beta, alpha = profile_variant(train, comp_train, self_ratio.get(aid), win, cap)
        pred = capacity(mu, cv, beta, alpha, market)
        ape = abs(pred - actual) / actual
        results[vn].append(ape)
        row[vn] = round(pred, 1)
    detail.append(row)

print(f"{'顾问':<8}{'实际4Q':>8}{'v1_doc':>9}{'v2_mu8':>9}{'v3_mu8cap':>10}")
for r in detail:
    print(f"{r['name']:<8}{r['actual']:>8}{r['v1_doc(mu4)']:>9}{r['v2_mu8']:>9}{r['v3_mu8_alphaCap']:>10}")
print()
for vn, apes in results.items():
    if apes:
        print(f"{vn:<18} MAPE={sum(apes)/len(apes):.1%}  中位APE={sorted(apes)[len(apes)//2]:.1%}  n={len(apes)}")
