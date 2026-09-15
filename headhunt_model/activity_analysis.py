# -*- coding: utf-8 -*-
"""推荐/面试活动 vs 业绩波动 分析
1) 按顾问x季度聚合: 推荐数(jobsubmission.dateAdded), 面试数(clientinterview.date)
2) 领先-滞后相关: 活动(t) vs 回款(t+k), k=0..3 (回款滞后约4-5个月)
3) 活动稳定性 vs 回款CV: 活动CV小的顾问回款是否更稳
4) 活动水平 vs mu: 活动量是否决定产能
"""
import sys, os, json, math
sys.path.insert(0, r"C:/Users/EDY/Documents/kimi/workspace/headhunt_model")
from step3_cleaning import clean_quarterly_revenue, clean_company_summary

CACHE = os.path.join(os.path.dirname(__file__), "activity_cache.json")

if os.path.exists(CACHE):
    act = json.load(open(CACHE, encoding="utf-8"))
else:
    sys.path.insert(0, r"C:/Users/EDY/.kimi/advanced_analysis_publish")
    from gllue_db_client import GllueDBClient
    from step2_collect import _CONFIG
    c = GllueDBClient(_CONFIG)
    act = {
        "recommend": c.query("""
            SELECT user_id AS advisor_id, YEAR(dateAdded) AS year, QUARTER(dateAdded) AS quarter,
                   COUNT(*) AS cnt
            FROM jobsubmission
            WHERE dateAdded >= '2021-01-01' AND user_id IS NOT NULL
            GROUP BY user_id, YEAR(dateAdded), QUARTER(dateAdded)
        """).to_dict("records"),
        "interview": c.query("""
            SELECT user_id AS advisor_id, YEAR(date) AS year, QUARTER(date) AS quarter,
                   COUNT(*) AS cnt
            FROM clientinterview
            WHERE date >= '2021-01-01' AND user_id IS NOT NULL
            GROUP BY user_id, YEAR(date), QUARTER(date)
        """).to_dict("records"),
    }
    json.dump(act, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, default=str)

raw = json.load(open(os.path.join(os.path.dirname(__file__), "raw_cache.json"), encoding="utf-8"))
advisors = clean_quarterly_revenue(raw["A"])
master = {str(a["advisor_id"]): a for a in raw["advisors"]}


def to_qmap(rows):
    m = {}
    for r in rows:
        m.setdefault(str(r["advisor_id"]), {})[(int(r["year"]), int(r["quarter"]))] = int(r["cnt"])
    return m


rec_map, itv_map = to_qmap(act["recommend"]), to_qmap(act["interview"])


def corr(xs, ys):
    n = len(xs)
    if n < 6:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx < 1e-9 or vy < 1e-9:
        return None
    return cov / math.sqrt(vx * vy)


# ---------- 1) 全样本汇集: 活动(t) vs 回款(t+k) ----------
def qidx(yq): return yq[0] * 4 + yq[1]
def fromidx(i): return (i // 4, i % 4) if i % 4 else (i // 4 - 1, 4)

print("=== 领先-滞后相关 (汇集全部有回款史的顾问) ===")
print(f"{'活动指标':<8}{'k=0(当季)':>10}{'k=+1':>8}{'k=+2':>8}{'k=+3':>8}{'k=+4':>8}")
for label, amap in [("推荐", rec_map), ("面试", itv_map)]:
    for label2 in [label]:
        pass
    row = []
    for k in range(0, 5):
        xs, ys = [], []
        for aid, adv in advisors.items():
            qs = adv["quarters"]
            aq = amap.get(aid, {})
            for yq, rev in qs.items():
                a_val = aq.get(fromidx(qidx(yq) - k), 0)
                xs.append(a_val)
                ys.append(rev)
        c = corr(xs, ys)
        row.append(f"{c:>8.3f}" if c is not None else "     n/a")
    print(f"{label:<8}" + "".join(row))

# ---------- 2) 顾问级: 活动量/活动CV vs 回款mu/CV ----------
print("\n=== 顾问级: 活动 vs 业绩 (ACTIVE, 近8季度) ===")
print(f"{'姓名':<8}{'推荐/季':>8}{'面试/季':>8}{'活动CV':>7}{'回款mu':>8}{'回款CV':>7}  {'推荐→次季回款r':>13}{'面试→次季回款r':>14}")
rows = []
for aid, adv in advisors.items():
    if master.get(aid, {}).get("status") != "Active":
        continue
    qs = adv["quarters"]
    keys = sorted(qs.keys())[-8:]
    revs = [qs[k] for k in keys]
    mu = sum(revs) / len(revs)
    sd = math.sqrt(sum((x - mu) ** 2 for x in revs) / len(revs))
    rcv = sd / mu if mu > 0 else 1.0

    recs = [rec_map.get(aid, {}).get(k, 0) for k in keys]
    itvs = [itv_map.get(aid, {}).get(k, 0) for k in keys]
    act_sum = [r + i for r, i in zip(recs, itvs)]
    am = sum(act_sum) / len(act_sum)
    asd = math.sqrt(sum((x - am) ** 2 for x in act_sum) / len(act_sum))
    acv = asd / am if am > 0 else 1.0

    # 活动(t) vs 回款(t+1) 顾问内相关
    r_rec = corr(recs[:-1], revs[1:])
    r_itv = corr(itvs[:-1], revs[1:])
    name = adv["name"]
    rows.append({"name": name, "rec_q": sum(recs) / 8, "itv_q": sum(itvs) / 8,
                 "acv": acv, "mu": mu, "rcv": rcv, "r_rec": r_rec, "r_itv": r_itv})
    print(f"{name:<8}{sum(recs)/8:>8.1f}{sum(itvs)/8:>8.1f}{acv:>7.2f}{mu:>8.1f}{rcv:>7.2f}"
          f"{(f'{r_rec:.2f}' if r_rec is not None else 'n/a'):>13}"
          f"{(f'{r_itv:.2f}' if r_itv is not None else 'n/a'):>14}")

# ---------- 3) 跨顾问横截面: 活动CV vs 回款CV, 活动量 vs mu ----------
xs_acv = [r["acv"] for r in rows]
ys_rcv = [r["rcv"] for r in rows]
xs_act = [r["rec_q"] + r["itv_q"] for r in rows]
ys_mu = [r["mu"] for r in rows]
print(f"\n=== 横截面相关 (n={len(rows)}) ===")
c1, c2 = corr(xs_acv, ys_rcv), corr(xs_act, ys_mu)
print(f"活动CV vs 回款CV: r={c1:.3f}  (活动越稳的人回款越稳?)" if c1 is not None else "n/a")
print(f"活动量 vs 回款mu: r={c2:.3f}  (活动越多的人产能越高?)" if c2 is not None else "n/a")
c3 = corr([r["rec_q"] for r in rows], ys_mu)
c4 = corr([r["itv_q"] for r in rows], ys_mu)
print(f"  其中 推荐量 vs mu: r={c3:.3f}   面试量 vs mu: r={c4:.3f}")
