# tests/test_candidate_notify.py
# 双问卷齐件通知闭环（AB 方案）: creator 穿透 / 完成事件 / 提交页反馈 / 审核页。
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api.main as api_main
from fastapi.testclient import TestClient

client = TestClient(api_main.app)

SELF_ANSWERS = {
    "perf_amount": 90, "perf_max_deal": 25, "perf_desc": "某CDMO总监单",
    "dom_tags": ["医学"], "dom_share": "医学100%",
    "speed_jc": "1-2天", "speed_case": "当天出mapping",
    "stab_moves": "1次", "stab_reason": "平台倒闭",
    "comp_share": "按规则分单",
}
HR_ANSWERS = {
    "perf_verify": "有部分佐证，数字合理", "perf_probe": "基本自洽，个别含糊",
    "dom_depth": "领域知识扎实", "speed_probe": "路径可行",
    "stab_verify": "基本可信", "comp_redline": "拒绝，边界感一般",
}


def _intake(name, created_by=""):
    r = client.post("/api/candidate/intake",
                    json={"name": name, "created_by": created_by})
    assert r.status_code == 200
    return r.json()


def _submit_pair(intake):
    self_token = intake["self_url"].split("/q/")[1]
    hr_token = intake["hr_url"].split("/h/")[1]
    s = client.post(f"/api/q/{self_token}/submit", json={"answers": SELF_ANSWERS})
    h = client.post(f"/api/h/{hr_token}/submit",
                    json={"answers": HR_ANSWERS, "interviewer": "测试HR"})
    return s, h


def test_intake_stores_created_by():
    intake = _intake("王五", created_by="ent_user_001")
    assert intake["status"] == "CREATED"
    candidates = client.get("/api/candidates").json()["candidates"]
    rec = next(c for c in candidates if c["cid"] == intake["cid"])
    assert rec["created_by"] == "ent_user_001"
    assert rec["completion_notified_at"] is None
    assert rec["hr_reviewed_at"] is None


def test_submit_responses_carry_peer_feedback():
    intake = _intake("赵六")
    self_token = intake["self_url"].split("/q/")[1]
    s = client.post(f"/api/q/{self_token}/submit", json={"answers": SELF_ANSWERS})
    assert s.status_code == 200
    assert s.json()["peer_submitted"] is False
    hr_token = intake["hr_url"].split("/h/")[1]
    h = client.post(f"/api/h/{hr_token}/submit",
                    json={"answers": HR_ANSWERS, "interviewer": "测试HR"})
    body = h.json()
    assert body["peer_submitted"] is True
    assert body["query"] == "赵六 的定岗定级"
    assert body["agent_url"].startswith("http")
    assert "/r/" in body["review_url"]


def test_completion_notify_fires_once_with_creator(monkeypatch):
    calls = []

    class _Resp:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        calls.append(req)
        return _Resp()

    monkeypatch.setenv("FEDERATION_QUESTIONNAIRE_EVENT_URL",
                       "http://fed.test/bff/headhunt/questionnaire-events")
    monkeypatch.setenv("HEADHUNT_EVENT_TOKEN", "test-secret")
    monkeypatch.setattr(api_main, "_urlopen", fake_urlopen)

    intake = _intake("孙七", created_by="ent_user_002")
    _submit_pair(intake)
    assert len(calls) == 1
    req = calls[0]
    assert req.headers["X-headhunt-event-token"] == "test-secret"
    import json as _json
    payload = _json.loads(req.data.decode("utf-8"))
    assert payload["created_by"] == "ent_user_002"
    assert payload["name"] == "孙七"
    assert payload["review_url"].startswith(
        os.environ.get("HEADHUNT_PUBLIC_BASE", "https://www.hiijob.cn"))

    # 幂等: 手动重放不再重复发（completion_notified_at 已落）
    r = client.post(f"/api/candidate/{intake['cid']}/notify-completion")
    assert r.status_code == 200
    assert len(calls) == 1


def test_notify_skipped_without_event_url(monkeypatch):
    monkeypatch.delenv("FEDERATION_QUESTIONNAIRE_EVENT_URL", raising=False)
    intake = _intake("周八")
    s, h = _submit_pair(intake)
    assert s.status_code == 200 and h.status_code == 200
    assert h.json()["completion_notified"] is False
    # 手动重放: 未配置事件地址 → 502 而非静默成功
    r = client.post(f"/api/candidate/{intake['cid']}/notify-completion")
    assert r.status_code == 502


def test_review_page_and_confirm_flow():
    intake = _intake("吴九")
    _submit_pair(intake)
    # review token 从存储层取（不经公开列表端点泄漏）
    from candidate.store import get as store_get
    rec = store_get(intake["cid"])
    review_token = rec["review_token"]

    page = client.get(f"/r/{review_token}")
    assert page.status_code == 200 and "问卷审核" in page.text

    bad = client.get("/api/r/not-a-token/review")
    assert bad.status_code == 404

    review = client.get(f"/api/r/{review_token}/review")
    assert review.status_code == 200
    body = review.json()
    assert body["name"] == "吴九"
    assert body["self"]["answers"]["perf_amount"] == 90
    assert body["hr"]["answers"]["dom_depth"] == "领域知识扎实"
    assert body["hr_reviewed_at"] is None
    assert body["query"] == "吴九 的定岗定级"

    c1 = client.post(f"/api/r/{review_token}/confirm")
    assert c1.status_code == 200 and c1.json()["hr_reviewed_at"]
    # 幂等: 二次确认时间不变
    c2 = client.post(f"/api/r/{review_token}/confirm")
    assert c2.json()["hr_reviewed_at"] == c1.json()["hr_reviewed_at"]
