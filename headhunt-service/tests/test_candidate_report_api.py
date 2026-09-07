"""Internal candidate report and idempotent assessment API contracts."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api.main import app, load_template
from candidate import store
from candidate.questionnaire import score_questionnaire


client = TestClient(app)
INTERNAL_HEADERS = {"X-Headhunt-Internal-Token": "report-api-secret"}

SELF_ANSWERS = {
    "perf_amount": 90,
    "perf_max_deal": 25,
    "perf_desc": "某CDMO总监单",
    "dom_tags": ["医学"],
    "dom_share": "医学100%",
    "speed_jc": "1-2天",
    "speed_case": "当天出mapping",
    "stab_moves": "1次",
    "stab_reason": "平台倒闭",
    "comp_share": "按规则分单",
}
HR_ANSWERS = {
    "perf_verify": "有部分佐证，数字合理",
    "perf_probe": "基本自洽，个别含糊",
    "dom_depth": "领域知识扎实",
    "speed_probe": "路径可行",
    "stab_verify": "基本可信",
    "comp_redline": "拒绝，边界感一般",
}


def _ready_candidate(name: str) -> str:
    rec = store.new_candidate(name)
    template = load_template()
    store.save_json(
        rec["cid"],
        "self_assess.json",
        {
            "answers": SELF_ANSWERS,
            "scored": score_questionnaire(template, SELF_ANSWERS, "self"),
        },
    )
    store.save_json(
        rec["cid"],
        "hr_assess.json",
        {
            "answers": HR_ANSWERS,
            "scored": score_questionnaire(template, HR_ANSWERS, "hr"),
            "interviewer": "Steven",
        },
    )
    store.update(rec["cid"], self_submitted_at="self", hr_submitted_at="hr")
    return rec["cid"]


def _report_payload(cid: str) -> dict:
    return {
        "schema_version": "candidate_assessment_report_v1",
        "report_id": "car_api_0001",
        "report_version": 1,
        "cid": cid,
        "workflow_id": "wf_api_0001",
        "workflow_run_id": "wfr_api_0001",
        "input_snapshot_hash": "sha256:" + "d" * 64,
        "assessment_version_id": "cav_" + "e" * 24,
        "renderer_version": "candidate-assessment-html-v1",
        "generator": {
            "workflow_key": "candidate_assessment_report",
            "workflow_version": "2026-09-07.1",
            "prompt_version": "candidate-assessment-report-v1",
        },
        "created_by": "user_steven",
        "confirmed_by": "user_steven",
        "created_at": "2026-09-07T10:00:00+00:00",
        "report": {
            "schema_version": "candidate_assessment_report_v1",
            "executive_summary": "完整评估报告",
            "source_snapshot_hash": "sha256:" + "d" * 64,
        },
    }


def test_assessment_replays_for_same_sources_and_changes_for_new_source() -> None:
    cid = _ready_candidate("幂等评估")

    first = client.post(f"/api/candidate/{cid}/assess")
    second = client.post(f"/api/candidate/{cid}/assess")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert first.json()["assessment_version_id"].startswith("cav_")
    assert first.json()["source_versions"]["self"].startswith("sha256:")

    changed = store.load_json(cid, "self_assess.json")
    changed["answers"] = {**changed["answers"], "perf_amount": 95}
    store.save_json(cid, "self_assess.json", changed)
    third = client.post(f"/api/candidate/{cid}/assess")
    assert third.status_code == 200
    assert third.json()["assessment_version_id"] != first.json()["assessment_version_id"]

    detail = client.get(f"/api/candidate/{cid}").json()
    assert detail["latest_assessment_version_id"] == third.json()["assessment_version_id"]


def test_assessment_rejects_mixed_template_versions() -> None:
    cid = _ready_candidate("模板冲突")
    mixed = store.load_json(cid, "hr_assess.json")
    mixed["scored"] = {**mixed["scored"], "template_version": 4}
    store.save_json(cid, "hr_assess.json", mixed)

    response = client.post(f"/api/candidate/{cid}/assess")

    assert response.status_code == 409
    assert response.json()["detail"] == "questionnaire_template_version_mismatch"


def test_assessment_replay_repairs_a_missing_profile_pointer() -> None:
    cid = _ready_candidate("评估恢复")
    first = client.post(f"/api/candidate/{cid}/assess").json()
    store.update(cid, assessed_at=None, latest_assessment_version_id=None)

    replay = client.post(f"/api/candidate/{cid}/assess")

    assert replay.status_code == 200
    assert replay.json() == first
    repaired = store.get(cid)
    assert repaired["latest_assessment_version_id"] == first["assessment_version_id"]
    assert repaired["assessed_at"]


def test_internal_report_routes_require_auth_and_archive_exact_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEADHUNT_INTERNAL_SECRET", "report-api-secret")
    cid = store.new_candidate("报告接口")["cid"]
    payload = _report_payload(cid)
    path = f"/api/internal/candidate/{cid}/reports"

    assert client.post(path, json=payload).status_code == 401
    assert client.post(
        path,
        headers={"X-Headhunt-Internal-Token": "wrong"},
        json=payload,
    ).status_code == 401

    created = client.post(path, headers=INTERNAL_HEADERS, json=payload)
    replay = client.post(path, headers=INTERNAL_HEADERS, json=payload)
    assert created.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == created.json()
    assert created.json()["artifact_hash"].startswith("sha256:")

    read = client.get(
        f"{path}/car_api_0001/versions/1",
        headers=INTERNAL_HEADERS,
    )
    assert read.status_code == 200
    assert read.json() == created.json()


def test_internal_report_route_rejects_identity_and_overwrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEADHUNT_INTERNAL_SECRET", "report-api-secret")
    cid = store.new_candidate("报告冲突")["cid"]
    path = f"/api/internal/candidate/{cid}/reports"

    wrong_identity = _report_payload("c999999999999999999")
    identity = client.post(path, headers=INTERNAL_HEADERS, json=wrong_identity)
    assert identity.status_code == 409
    assert identity.json()["detail"] == "report_identity_mismatch"

    original = _report_payload(cid)
    assert client.post(path, headers=INTERNAL_HEADERS, json=original).status_code == 200
    changed = _report_payload(cid)
    changed["report"]["executive_summary"] = "覆盖内容"
    overwrite = client.post(path, headers=INTERNAL_HEADERS, json=changed)
    assert overwrite.status_code == 409
    assert overwrite.json()["detail"] == "report_version_conflict"
