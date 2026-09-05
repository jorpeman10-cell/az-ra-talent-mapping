# tests/test_candidate_api.py
# API flow tests via TestClient. Paths come from tests/conftest.py.
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

SELF_ANSWERS = {
    "perf_amount": 90, "perf_max_deal": 25, "perf_desc": "某CDMO总监单",
    "dom_tags": ["肿瘤"], "dom_share": "肿瘤100%",
    "speed_jc": "1-2天", "speed_case": "当天出mapping",
    "stab_moves": "1次", "stab_reason": "平台倒闭",
    "comp_share": "按规则分单",
}
HR_ANSWERS = {
    "perf_verify": "有部分佐证，数字合理", "perf_probe": "基本自洽，个别含糊",
    "dom_depth": "领域知识扎实",
    "speed_probe": "路径可行",
    "stab_verify": "基本可信",
    "comp_redline": "拒绝，边界感一般",
}


def test_intake_and_template_flow():
    r = client.post("/api/candidate/intake", json={"name": "张三", "target_line": "肿瘤线"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "CREATED" and body["self_url"].startswith("/q/")
    t = client.get(f"/api{body['self_url']}/template")
    assert t.status_code == 200
    assert t.json()["candidate_name"] == "张三"
    assert "dimensions" in t.json()["template"]


def test_submit_self_then_token_dead():
    r = client.post("/api/candidate/intake", json={"name": "李四"})
    token = r.json()["self_url"].split("/q/")[1]
    s = client.post(f"/api/q/{token}/submit", json={"answers": SELF_ANSWERS})
    assert s.status_code == 200 and s.json()["status"] == "SELF_DONE"
    again = client.post(f"/api/q/{token}/submit", json={"answers": SELF_ANSWERS})
    assert again.status_code == 410          # single use
    t2 = client.get(f"/api/q/{token}/template")
    assert t2.status_code == 410


def test_bad_token_404():
    # page is always served; the API validates and reports the reason
    assert client.get("/q/nope").status_code == 200
    assert client.get("/api/q/nope/template").status_code == 404


def test_bad_cid_rejected():
    assert client.get("/api/candidate/cXXX").status_code == 422
    assert client.post("/api/candidate/c123/hr-assess",
                       json={"answers": {}}).status_code == 422


def test_hr_assess_and_detail():
    r = client.post("/api/candidate/intake", json={"name": "王五"})
    token = r.json()["self_url"].split("/q/")[1]
    cid = r.json()["cid"]
    client.post(f"/api/q/{token}/submit", json={"answers": SELF_ANSWERS})
    h = client.post(f"/api/candidate/{cid}/hr-assess",
                    json={"answers": HR_ANSWERS, "interviewer": "Steven"})
    assert h.status_code == 200 and h.json()["status"] == "HR_DONE"
    d = client.get(f"/api/candidate/{cid}")
    assert d.status_code == 200
    rec = d.json()
    assert rec["profile"]["name"] == "王五"
    assert rec["self_assess"]["scored"]["role"] == "self"
    assert rec["hr_assess"]["scored"]["role"] == "hr"
    lst = client.get("/api/candidates").json()["candidates"]
    assert any(c["cid"] == cid for c in lst)


def test_hr_assess_missing_candidate():
    # well-formed cid (c + 14 digits + 4 hex) that does not exist -> 404
    assert client.post("/api/candidate/c999999999999999999/hr-assess",
                       json={"answers": HR_ANSWERS}).status_code == 404


def test_board_still_works():
    # existing endpoints untouched: index served
    assert client.get("/").status_code == 200


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
