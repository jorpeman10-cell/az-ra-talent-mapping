"""Workflow facts and questionnaire-token rotation contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from candidate import store


client = TestClient(app)


def _archive_response(cid: str, role: str, marker: str) -> None:
    store.save_json(
        cid,
        f"{role}_assess.json",
        {
            "answers": {"evidence": marker},
            "scored": {"role": role, "template_version": 3},
        },
    )
    store.update(cid, **{f"{role}_submitted_at": f"2026-09-07T0{len(marker)}:00:00+00:00"})


def test_workflow_facts_track_both_responses_independently() -> None:
    rec = store.new_candidate("双问卷")

    empty = store.candidate_workflow_facts(rec["cid"])
    assert empty["completion"] == {"self": False, "hr": False}
    assert empty["source_versions"] == {"self": None, "hr": None}

    _archive_response(rec["cid"], "hr", "HR first")
    hr_only = store.candidate_workflow_facts(rec["cid"])
    assert hr_only["completion"] == {"self": False, "hr": True}
    assert hr_only["source_versions"]["self"] is None
    assert hr_only["source_versions"]["hr"].startswith("sha256:")

    _archive_response(rec["cid"], "self", "self second")
    both = store.candidate_workflow_facts(rec["cid"])
    assert both["completion"] == {"self": True, "hr": True}
    assert both["source_versions"]["self"].startswith("sha256:")
    assert both["source_versions"]["hr"] == hr_only["source_versions"]["hr"]


def test_source_version_is_canonical_and_changes_with_archived_content() -> None:
    rec = store.new_candidate("版本哈希")
    first = {
        "answers": {"b": 2, "a": 1},
        "scored": {"template_version": 3, "role": "self"},
    }
    store.save_json(rec["cid"], "self_assess.json", first)
    store.update(rec["cid"], self_submitted_at="submitted")
    first_hash = store.candidate_workflow_facts(rec["cid"])["source_versions"]["self"]

    reordered = {
        "scored": {"role": "self", "template_version": 3},
        "answers": {"a": 1, "b": 2},
    }
    store.save_json(rec["cid"], "self_assess.json", reordered)
    reordered_hash = store.candidate_workflow_facts(rec["cid"])["source_versions"]["self"]
    assert reordered_hash == first_hash

    store.save_json(rec["cid"], "self_assess.json", {**reordered, "answers": {"a": 9}})
    changed_hash = store.candidate_workflow_facts(rec["cid"])["source_versions"]["self"]
    assert changed_hash != first_hash


def test_rotate_expired_unused_self_token_invalidates_the_old_token() -> None:
    rec = store.new_candidate("重发链接")
    old_token = rec["token"]
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    store.update(
        rec["cid"],
        token_expires_at=(now - timedelta(seconds=1)).isoformat(),
    )

    rotated = store.rotate_questionnaire_token(rec["cid"], "self", now=now)

    assert rotated["role"] == "self"
    assert rotated["token"] != old_token
    assert rotated["expires_at"] == (now + timedelta(hours=48)).isoformat()
    assert store.validate_token(old_token, now=now) == (None, "not_found")
    assert store.validate_token(rotated["token"], now=now) == (rec["cid"], None)


@pytest.mark.parametrize("role", ["self", "hr"])
def test_rotation_rejects_unexpired_or_submitted_questionnaire(role: str) -> None:
    rec = store.new_candidate(f"不可重发-{role}")
    with pytest.raises(ValueError, match="questionnaire_not_expired"):
        store.rotate_questionnaire_token(rec["cid"], role)

    store.update(rec["cid"], **{f"{role}_submitted_at": "submitted"})
    with pytest.raises(ValueError, match="questionnaire_already_submitted"):
        store.rotate_questionnaire_token(rec["cid"], role)


def test_rotation_rejects_unknown_role_and_candidate() -> None:
    rec = store.new_candidate("参数校验")
    with pytest.raises(ValueError, match="questionnaire_role_invalid"):
        store.rotate_questionnaire_token(rec["cid"], "manager")
    with pytest.raises(LookupError, match="candidate_not_found"):
        store.rotate_questionnaire_token("c999999999999999999", "self")


def test_candidate_detail_exposes_facts_without_raw_questionnaire_tokens() -> None:
    rec = client.post("/api/candidate/intake", json={"name": "详情安全"}).json()
    detail = client.get(f"/api/candidate/{rec['cid']}")

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["completion"] == {"self": False, "hr": False}
    assert payload["source_versions"] == {"self": None, "hr": None}
    assert payload["questionnaire"]["template_id"] == "consultant_v1"
    assert payload["questionnaire"]["template_version"] >= 1
    assert "token" not in payload["profile"]
    assert "hr_token" not in payload["profile"]


def test_candidate_detail_pins_the_archived_response_template_version() -> None:
    rec = client.post("/api/candidate/intake", json={"name": "版本绑定"}).json()
    _archive_response(rec["cid"], "self", "self")
    _archive_response(rec["cid"], "hr", "hr")

    payload = client.get(f"/api/candidate/{rec['cid']}").json()

    assert payload["questionnaire"]["template_id"] == "consultant_v1"
    assert payload["questionnaire"]["template_version"] == 3


def test_internal_rotation_route_requires_secret_and_returns_only_new_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEADHUNT_INTERNAL_SECRET", "workflow-test-secret")
    rec = client.post("/api/candidate/intake", json={"name": "内部重发"}).json()
    cid = rec["cid"]
    stored = store.get(cid)
    store.update(
        cid,
        token_expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    )

    assert client.post(
        f"/api/internal/candidate/{cid}/questionnaire-token/rotate",
        json={"role": "self"},
    ).status_code == 401
    assert client.post(
        f"/api/internal/candidate/{cid}/questionnaire-token/rotate",
        headers={"X-Headhunt-Internal-Token": "wrong"},
        json={"role": "self"},
    ).status_code == 401

    response = client.post(
        f"/api/internal/candidate/{cid}/questionnaire-token/rotate",
        headers={"X-Headhunt-Internal-Token": "workflow-test-secret"},
        json={"role": "self"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"cid", "role", "url", "expires_at"}
    assert body["cid"] == cid
    assert body["url"].startswith("/q/")
    assert stored["token"] not in body["url"]


def test_internal_rotation_route_maps_conflicts_and_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEADHUNT_INTERNAL_SECRET", "workflow-test-secret")
    rec = client.post("/api/candidate/intake", json={"name": "重发冲突"}).json()
    headers = {"X-Headhunt-Internal-Token": "workflow-test-secret"}

    active = client.post(
        f"/api/internal/candidate/{rec['cid']}/questionnaire-token/rotate",
        headers=headers,
        json={"role": "self"},
    )
    assert active.status_code == 409
    assert active.json()["detail"] == "questionnaire_not_expired"

    invalid_role = client.post(
        f"/api/internal/candidate/{rec['cid']}/questionnaire-token/rotate",
        headers=headers,
        json={"role": "manager"},
    )
    assert invalid_role.status_code == 422
