# -*- coding: utf-8 -*-
"""黄金样本回归: 用缓存数据重跑管线, 与 golden_board.json 逐字段比对(容差0.01)
生成/更新 golden: python -m tests.test_golden --update
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.run import run_pipeline

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(BASE, "tests", "golden_board.json")
CONFIG = os.path.join(BASE, "config", "config.yaml")


def snapshot():
    res = run_pipeline(CONFIG, use_cache=True)
    snap = {}
    byid = {a["advisor_id"]: a for a in res["advisors"]}
    for r in res["board"]["advisors"]:
        d = byid[r["advisor_id"]]
        snap[r["advisor_id"]] = {
            "name": r["name"], "decision": r["decision"],
            "conservative": r["conservative"], "rank_score": r["rank_score"],
            "mu": d["profile"]["mu"], "cv": d["profile"]["cv"],
            "beta": d["profile"]["beta"], "alpha": d["profile"]["alpha"],
            "emp_npv": d["models"]["employ"]["npv_3y"],
            "margin_y1": d["models"]["employ"]["margin_y1"],
            "inc_npv": d["models"]["incubate"]["npv_3y"],
        }
    return {"market_phase": res["board"]["market_phase"],
            "market_slope": res["board"]["market_slope"],
            "advisors": snap}


def test_golden():
    golden = json.load(open(GOLDEN, encoding="utf-8"))
    cur = snapshot()
    assert cur["market_phase"] == golden["market_phase"], "market_phase 漂移"
    assert abs(cur["market_slope"] - golden["market_slope"]) < 0.01
    for aid, g in golden["advisors"].items():
        c = cur["advisors"].get(aid)
        assert c, f"{g['name']} 不在看板中"
        assert c["decision"] == g["decision"], f"{g['name']} 决策漂移 {g['decision']}->{c['decision']}"
        for k in ("conservative", "mu", "emp_npv", "margin_y1", "inc_npv"):
            assert abs(c[k] - g[k]) < 0.01, f"{g['name']} 字段 {k} 漂移 {g[k]}->{c[k]}"


if __name__ == "__main__":
    if "--update" in sys.argv:
        snap = snapshot()
        json.dump(snap, open(GOLDEN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"golden 已更新: {len(snap['advisors'])} 名顾问")
    else:
        test_golden()
        print("黄金样本回归通过")
