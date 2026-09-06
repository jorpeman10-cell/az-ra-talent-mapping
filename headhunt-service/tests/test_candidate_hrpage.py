# tests/test_candidate_hrpage.py
# HR interview-assess form page (/h/{token}) — mirrors the /q/ self flow but
# with an independent 7d hr_token. Paths/env come from tests/conftest.py.
import os, sys
from datetime import timedelta, timezone
from datetime import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from api.main import app
from candidate import store
from candidate.store import validate_token, validate_hr_token, get as get_candidate, \
    update as update_candidate

client = TestClient(app)

HR_ANSWERS = {
    "perf_verify": "有部分佐证，数字合理", "perf_probe": "基本自洽，个别含糊",
    "dom_depth": "领域知识扎实",
    "speed_probe": "路径可行",
    "stab_verify": "基本可信",
    "comp_redline": "拒绝，边界感一般",
}


def _intake(name="赵六"):
    r = client.post("/api/candidate/intake", json={"name": name})
    assert r.status_code == 200
    return r.json()


def test_intake_returns_hr_url():
    body = _intake()
    assert body["hr_url"].startswith("/h/")
    rec = get_candidate(body["cid"])
    assert rec["hr_token"] == body["hr_url"].split("/h/")[1]
    assert rec["hr_token_expires_at"]          # 7d, stored on profile


def test_hr_token_7d_not_self_48h():
    body = _intake()
    hr_tok = body["hr_url"].split("/h/")[1]
    self_tok = body["self_url"].split("/q/")[1]
    later = dt.now(timezone.utc) + timedelta(hours=72)   # beyond 48h, within 7d
    cid, reason = validate_hr_token(hr_tok, now=later)
    assert cid == body["cid"] and reason is None         # hr token still alive
    assert validate_token(self_tok, now=later) == (None, "expired")  # self is not
    assert validate_hr_token(self_tok) == (None, "not_found")        # hr is not self


def test_hr_page_always_served():
    body = _intake()
    assert client.get(body["hr_url"]).status_code == 200
    assert client.get("/h/nope").status_code == 200      # page even for bad token


def test_hr_template_flow():
    body = _intake()
    r = client.get(f"/api{body['hr_url']}/template")
    assert r.status_code == 200
    j = r.json()
    assert j["candidate_name"] == "赵六"
    assert j["expires_at"] == get_candidate(body["cid"])["hr_token_expires_at"]
    assert "dimensions" in j["template"]
    assert any(d.get("hr_questions") for d in j["template"]["dimensions"])


def test_hr_submit_archives_and_advances():
    body = _intake()
    cid, hr_tok = body["cid"], body["hr_url"].split("/h/")[1]
    r = client.post(f"/api/h/{hr_tok}/submit",
                    json={"answers": HR_ANSWERS, "interviewer": "Steven"})
    assert r.status_code == 200 and r.json()["status"] == "HR_DONE"
    rec = get_candidate(cid)
    assert rec["hr_submitted_at"] and store.derive_status(rec) == "HR_DONE"
    archived = store.load_json(cid, "hr_assess.json")
    assert archived["scored"]["role"] == "hr"
    assert archived["interviewer"] == "Steven"
    assert archived["submitted_at"]


def test_hr_submit_independent_of_self():
    # hr submission alone does not kill the self token (separate semantics)
    body = _intake()
    cid, hr_tok = body["cid"], body["hr_url"].split("/h/")[1]
    client.post(f"/api/h/{hr_tok}/submit",
                json={"answers": HR_ANSWERS, "interviewer": "Kimbort"})
    cid2, reason = validate_token(body["self_url"].split("/q/")[1])
    assert cid2 == cid and reason is None


def test_hr_submit_twice_410():
    body = _intake()
    hr_tok = body["hr_url"].split("/h/")[1]
    s1 = client.post(f"/api/h/{hr_tok}/submit",
                     json={"answers": HR_ANSWERS, "interviewer": "Steven"})
    assert s1.status_code == 200
    s2 = client.post(f"/api/h/{hr_tok}/submit",
                     json={"answers": HR_ANSWERS, "interviewer": "Steven"})
    assert s2.status_code == 410
    assert client.get(f"/api/h/{hr_tok}/template").status_code == 410


def test_hr_unknown_token_404():
    assert client.get("/api/h/nope/template").status_code == 404
    assert client.post("/api/h/nope/submit",
                       json={"answers": HR_ANSWERS}).status_code == 404


def test_hr_expired_410():
    body = _intake()
    hr_tok = body["hr_url"].split("/h/")[1]
    # store-level: 8 days past issuance -> expired
    later = dt.now(timezone.utc) + timedelta(days=8)
    assert validate_hr_token(hr_tok, now=later) == (None, "expired")
    # endpoint-level: rewrite expiry into the past -> 410
    update_candidate(body["cid"],
                     hr_token_expires_at=dt.now(timezone.utc).isoformat())
    assert client.get(f"/api/h/{hr_tok}/template").status_code == 410


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
