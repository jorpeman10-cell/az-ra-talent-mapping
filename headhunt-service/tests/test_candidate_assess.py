# tests/test_candidate_assess.py
# assess endpoint: guards, wiring of internal samples from tmp CSV + grade map.
# Env dirs come from tests/conftest.py; seeding is request-time (endpoint reads
# files at request time, not import time), so import order does not matter.
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient

TMP = os.environ["HEADHUNT_DATA_DIR"]
CFG = os.environ["HEADHUNT_CONFIG_DIR"]
os.makedirs(CFG, exist_ok=True)
SALARY_CSV = os.path.join(TMP, "salary.csv")
with open(SALARY_CSV, "w", encoding="utf-8-sig", newline="") as f:
    f.write("表头行\n姓名,月工资,职位工资,津贴,五险一金\n")  # 2 header rows per format
    f.write(",张三,15000,0,0,4000\n,李四,17000,0,0,4500\n")
with open(os.path.join(CFG, "candidate_grade_map.json"), "w", encoding="utf-8") as f:
    json.dump({"_comment": "test", "mapping": {"张三": "C1", "李四": "C1"}}, f, ensure_ascii=False)
with open(os.path.join(CFG, "market_anchors.json"), "w", encoding="utf-8") as f:
    json.dump({"_comment": "test", "anchors": {}}, f, ensure_ascii=False)
os.environ["HEADHUNT_SALARY_CSV"] = SALARY_CSV  # endpoint reads env override first

from api.main import app
client = TestClient(app)

SELF = {"perf_amount": 90, "perf_max_deal": 25, "perf_desc": "x",
        "dom_tags": ["医学"], "dom_share": "医学100%", "speed_jc": "1-2天",
        "speed_case": "x", "stab_moves": "1次", "stab_reason": "x", "comp_share": "按规则分单"}
HR = {"perf_verify": "有部分佐证，数字合理", "perf_probe": "基本自洽，个别含糊",
      "dom_depth": "领域知识扎实", "speed_probe": "路径可行",
      "stab_verify": "基本可信", "comp_redline": "拒绝，边界感一般"}


def _full_candidate(name):
    r = client.post("/api/candidate/intake", json={"name": name}).json()
    client.post(f"/api/q/{r['self_url'].split('/q/')[1]}/submit", json={"answers": SELF})
    client.post(f"/api/candidate/{r['cid']}/hr-assess", json={"answers": HR})
    return r["cid"]


def test_assess_blocks_when_incomplete():
    r = client.post("/api/candidate/intake", json={"name": "甲"}).json()
    resp = client.post(f"/api/candidate/{r['cid']}/assess")
    assert resp.status_code == 409


def test_assess_happy_path():
    cid = _full_candidate("乙")
    resp = client.post(f"/api/candidate/{cid}/assess")
    assert resp.status_code == 200
    out = resp.json()
    # 90 * 0.9 = 81 -> SC1 base, dom 4 + overlap 100 -> +0.5 -> SC2 (see P0 case)
    assert out["leveling"]["effective_billing_wan"] == 81.0
    assert out["status"] == "OK"
    # internal samples from grade map: C1 = [15000, 17000] -> median p50 16000
    assert out["band"]["p50"] == 16000
    assert out["breakeven_wan"] > 0
    d = client.get(f"/api/candidate/{cid}").json()
    assert d["profile"]["status"] == "ASSESSED"
    assert d["latest_assessment"]["leveling"]["effective_billing_wan"] == 81.0


def test_assess_empty_internal_data_guard():
    # wipe grade map -> internal samples empty -> band no_internal_data, breakeven None, warning
    with open(os.path.join(CFG, "candidate_grade_map.json"), "w", encoding="utf-8") as f:
        json.dump({"_comment": "x", "mapping": {}}, f, ensure_ascii=False)
    cid = _full_candidate("丙")
    out = client.post(f"/api/candidate/{cid}/assess").json()
    assert out["band"]["source"] == "no_internal_data"
    assert out["breakeven_wan"] is None
    assert any("grade_map" in w for w in out["warnings"])


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
