# tests/test_candidate_e2e.py
# Full flow: intake -> template -> self submit -> hr assess -> assess -> archive files.
# Env dirs come from tests/conftest.py.
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
TMP = os.environ["HEADHUNT_DATA_DIR"]
from api.main import app

client = TestClient(app)

SELF = {"perf_amount": 90, "perf_max_deal": 25, "perf_desc": "某CDMO管线总监单，客户续约二期",
        "dom_tags": ["肿瘤", "糖尿病/CVRM"], "dom_share": "肿瘤70% 糖尿病30%",
        "speed_jc": "1-2天", "speed_case": "接到JC当天出mapping次日首推",
        "stab_moves": "1次", "stab_reason": "原平台团队解散", "comp_share": "按规则分单"}
HR = {"perf_verify": "有部分佐证，数字合理", "perf_probe": "基本自洽，个别含糊",
      "dom_depth": "领域知识扎实", "speed_probe": "路径可行",
      "stab_verify": "基本可信", "comp_redline": "拒绝，边界感一般"}


def test_e2e_full_flow():
    r = client.post("/api/candidate/intake",
                    json={"name": "e2e测试候选人", "target_line": "肿瘤线", "notes": "e2e"}).json()
    cid, token = r["cid"], r["self_url"].split("/q/")[1]

    page = client.get(f"/q/{token}")
    assert page.status_code == 200 and "问卷" in page.text

    tpl = client.get(f"/api/q/{token}/template").json()
    assert tpl["candidate_name"] == "e2e测试候选人"

    s = client.post(f"/api/q/{token}/submit", json={"answers": SELF})
    assert s.status_code == 200

    h = client.post(f"/api/candidate/{cid}/hr-assess",
                    json={"answers": HR, "interviewer": "e2e"})
    assert h.status_code == 200

    a = client.post(f"/api/candidate/{cid}/assess")
    assert a.status_code == 200
    out = a.json()
    assert out["status"] == "OK"
    assert out["leveling"]["verify_coefficient"] == 0.9
    assert out["line_match"]["top_line"] in ("肿瘤线", "糖尿病线")

    d = client.get(f"/api/candidate/{cid}").json()
    assert d["profile"]["status"] == "ASSESSED"
    assert d["self_assess"]["scored"]["template_version"] >= 1
    assert d["hr_assess"]["scored"]["role"] == "hr"
    # archive files on disk
    cdir = os.path.join(TMP, "candidates", cid)
    files = os.listdir(cdir)
    assert "profile.json" in files and "self_assess.json" in files and "hr_assess.json" in files
    assert any(f.startswith("assessment_") for f in files)


def test_e2e_redline_reject():
    r = client.post("/api/candidate/intake", json={"name": "红线测试"}).json()
    cid, token = r["cid"], r["self_url"].split("/q/")[1]
    client.post(f"/api/q/{token}/submit", json={"answers": SELF})
    client.post(f"/api/candidate/{cid}/hr-assess",
                json={"answers": dict(HR, comp_redline="承认做过类似行为")})
    out = client.post(f"/api/candidate/{cid}/assess").json()
    assert out["status"] == "REJECT_REVIEW"


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
