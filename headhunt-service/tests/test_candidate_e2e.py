# tests/test_candidate_e2e.py
# Full flow: intake -> template -> self submit -> hr assess -> assess -> archive files.
# Env dirs come from tests/conftest.py.
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys


CONTRACT_SCHEMA_VERSION = "candidate_assessment_headhunt_contract_v1"
# Updated only after the independently tracked Federation artifact is canonicalized.
CONTRACT_SHA256 = "83bcf19ac27dbc3cd649ebb05fa5be6449e5f73575295186fd9a189ae7f13845"


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _content_version(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def candidate_assessment_contract_fixture() -> dict:
    """Return one deterministic, synthetic producer/consumer contract.

    The report and rotation responses are deliberately security projections:
    immutable identity/version facts are retained while the full report body
    and raw questionnaire URL token are represented only by hashes/prefixes.
    """

    cid = "c20260907090000abcd"
    workflow_id = "wf_candidate_contract_001"
    template_version = 3
    self_assess = {
        "answers": {
            "dom_tags": ["oncology"],
            "perf_amount": 90,
            "speed_case": "same-day mapping",
        },
        "scored": {
            "claimed_billing_wan": 90.0,
            "dimensions": {
                "collaboration_compliance": {"answers": {}, "score": 4.0},
                "domain_depth": {"answers": {}, "score": 4.0},
                "performance": {"answers": {}, "score": 5.0},
                "response_speed": {"answers": {}, "score": 5.0},
                "stability": {"answers": {}, "score": 4.0},
            },
            "domain_tags": ["oncology"],
            "redline": False,
            "role": "self",
            "template_version": template_version,
        },
        "submitted_at": "2026-09-07T09:10:00+00:00",
    }
    hr_assess = {
        "answers": {
            "dom_depth": "verified specialist network",
            "perf_verify": "verified delivery record",
            "speed_probe": "same-day response verified",
        },
        "interviewer": "Contract Reviewer",
        "scored": {
            "claimed_billing_wan": None,
            "dimensions": {
                "collaboration_compliance": {"answers": {}, "score": 4.0},
                "domain_depth": {"answers": {}, "score": 4.0},
                "performance": {"answers": {}, "score": 4.0},
                "response_speed": {"answers": {}, "score": 5.0},
                "stability": {"answers": {}, "score": 4.0},
            },
            "domain_tags": [],
            "redline": False,
            "role": "hr",
            "template_version": template_version,
        },
        "submitted_at": "2026-09-07T09:20:00+00:00",
    }
    source_versions = {
        "self": _content_version(self_assess),
        "hr": _content_version(hr_assess),
    }
    assessment_identity = {
        "cid": cid,
        "source_versions": source_versions,
        "template_version": template_version,
    }
    assessment_version_id = (
        "cav_"
        + hashlib.sha256(
            json.dumps(
                assessment_identity,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:24]
    )
    assessment = {
        "assessment_version_id": assessment_version_id,
        "band": {"p25": 18000, "p50": 20000, "p75": 23000},
        "confidence": "MEDIUM",
        "divergence": {"divergent": [], "high_divergence": False},
        "leveling": {"effective_billing_wan": 72.0, "grade": "C1"},
        "source_versions": source_versions,
        "status": "OK",
        "template_version": template_version,
    }
    detail = {
        "completion": {"hr": True, "self": True},
        "hr_assess": hr_assess,
        "latest_assessment": assessment,
        "latest_assessment_version_id": assessment_version_id,
        "profile": {
            "assessed_at": "2026-09-07T09:30:00+00:00",
            "cid": cid,
            "created_at": "2026-09-07T09:00:00+00:00",
            "hr_submitted_at": "2026-09-07T09:20:00+00:00",
            "hr_token_expires_at": "2026-09-14T09:00:00+00:00",
            "latest_assessment_version_id": assessment_version_id,
            "name": "Synthetic Candidate",
            "notes": "Synthetic contract data only",
            "self_submitted_at": "2026-09-07T09:10:00+00:00",
            "status": "ASSESSED",
            "target_line": "oncology",
            "token_expires_at": "2026-09-09T09:00:00+00:00",
        },
        "questionnaire": {
            "hr": {
                "expires_at": "2026-09-14T09:00:00+00:00",
                "submitted_at": "2026-09-07T09:20:00+00:00",
            },
            "self": {
                "expires_at": "2026-09-09T09:00:00+00:00",
                "submitted_at": "2026-09-07T09:10:00+00:00",
            },
            "template_id": "consultant_v1",
            "template_version": template_version,
        },
        "self_assess": self_assess,
        "source_versions": source_versions,
    }
    snapshot_without_hash = {
        "candidate": {
            "name": detail["profile"]["name"],
            "notes": detail["profile"]["notes"],
            "target_line": detail["profile"]["target_line"],
        },
        "cid": cid,
        "deterministic_assessment": {
            "assessment_version_id": assessment_version_id,
            "result": assessment,
        },
        "hr_response": {
            "answers": hr_assess["answers"],
            "interviewer": hr_assess["interviewer"],
            "scores": hr_assess["scored"],
            "submission_version": source_versions["hr"],
        },
        "questionnaire": {
            "template_id": "consultant_v1",
            "template_version": template_version,
        },
        "schema_version": "candidate_assessment_input_v1",
        "self_response": {
            "answers": self_assess["answers"],
            "scores": self_assess["scored"],
            "submission_version": source_versions["self"],
        },
        "workflow_id": workflow_id,
    }
    input_snapshot_hash = _content_version(snapshot_without_hash)
    report_id = (
        "car_"
        + hashlib.sha256(f"{workflow_id}:{input_snapshot_hash}".encode("utf-8"))
        .hexdigest()[:24]
    )
    report_artifact = {
        "assessment_version_id": assessment_version_id,
        "cid": cid,
        "confirmed_by": "synthetic-user",
        "created_at": "2026-09-07T10:00:00+00:00",
        "created_by": "federation",
        "generator": {
            "prompt_version": "candidate-assessment-report-v1",
            "workflow_key": "candidate_assessment_report",
            "workflow_version": "2026-09-07.1",
        },
        "input_snapshot_hash": input_snapshot_hash,
        "renderer_version": "candidate-assessment-html-v1",
        "report": {
            "schema_version": "candidate_assessment_report_v1",
            "source_snapshot_hash": input_snapshot_hash,
        },
        "report_id": report_id,
        "report_version": 1,
        "schema_version": "candidate_assessment_report_v1",
        "workflow_id": workflow_id,
        "workflow_run_id": f"{workflow_id}:attempt:1",
    }
    report_metadata = {
        "artifact_hash": _content_version(report_artifact),
        "assessment_version_id": assessment_version_id,
        "cid": cid,
        "input_snapshot_hash": input_snapshot_hash,
        "report_id": report_id,
        "report_schema_version": "candidate_assessment_report_v1",
        "report_version": 1,
        "workflow_id": workflow_id,
    }
    return {
        "assessment_metadata": {
            "assessment_version_id": assessment_version_id,
            "cid": cid,
            "source_versions": source_versions,
            "template_id": "consultant_v1",
            "template_version": template_version,
        },
        "candidate_detail": detail,
        "questionnaire_token_rotation": {
            "cid": cid,
            "expires_at": "2026-09-09T10:00:00+00:00",
            "raw_token_included": False,
            "role": "self",
            "url_path_prefix": "/q/",
        },
        "report_create": report_metadata,
        "report_read": dict(report_metadata),
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "workflow_id": workflow_id,
    }


def _assert_contract_is_sanitized(payload: dict) -> None:
    encoded = _canonical_json(payload).decode("utf-8").lower()
    for forbidden in (
        '"token":',
        '"hr_token":',
        '"authorization":',
        '"api_key":',
        '"share_token":',
        '"phone":',
        '"mobile":',
        '"email":',
    ):
        assert forbidden not in encoded
    rotation = payload["questionnaire_token_rotation"]
    assert rotation["raw_token_included"] is False
    assert set(rotation) == {
        "cid",
        "expires_at",
        "raw_token_included",
        "role",
        "url_path_prefix",
    }
    assert "report" not in payload["report_read"]


def _certify_external_contract(path: str) -> None:
    expected = _canonical_json(candidate_assessment_contract_fixture())
    actual = Path(path).read_bytes()
    assert actual == expected, "shared candidate-assessment fixture bytes differ"
    digest = hashlib.sha256(actual).hexdigest()
    assert digest == CONTRACT_SHA256, (digest, CONTRACT_SHA256)
    _assert_contract_is_sanitized(json.loads(actual))


if __name__ == "__main__" and len(sys.argv) >= 2:
    if sys.argv[1] == "--emit-contract":
        sys.stdout.buffer.write(_canonical_json(candidate_assessment_contract_fixture()))
        raise SystemExit(0)
    if len(sys.argv) == 3 and sys.argv[1] == "--certify-contract":
        _certify_external_contract(sys.argv[2])
        print(f"candidate assessment contract certified: sha256:{CONTRACT_SHA256}")
        raise SystemExit(0)

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


def test_cross_service_contract_fixture_is_deterministic_and_sanitized():
    payload = candidate_assessment_contract_fixture()
    _assert_contract_is_sanitized(payload)
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    assert digest == CONTRACT_SHA256
    assert payload["report_read"] == payload["report_create"]
    assert payload["candidate_detail"]["completion"] == {"self": True, "hr": True}


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
