# tests/test_candidate_e2e.py
# Full flow: intake -> template -> self submit -> hr assess -> assess -> archive files.
# Env dirs come from tests/conftest.py.
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from tempfile import TemporaryDirectory


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from candidate import report_store as candidate_report_store
from candidate import store as candidate_store
from candidate.questionnaire import DIM_IDS, default_template


CONTRACT_SCHEMA_VERSION = "candidate_assessment_headhunt_contract_v1"
# Updated only after the independently tracked Federation artifact is canonicalized.
# Frozen contract digest — intentionally updated 2026-09-14: questionnaire
# template v2 (CV questions) bumps the embedded template_version 1 -> 2.
CONTRACT_SHA256 = "25fadce2052d5a3069f740758635a7846c4407edbcce37131fff5c991cb2431c"


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


def _private_report(snapshot_hash: str) -> dict:
    dimensions = (
        "performance",
        "domain_depth",
        "response_speed",
        "stability",
        "collaboration_compliance",
    )
    evidence = {
        "performance": ["self:perf_amount", "hr:perf_verify"],
        "domain_depth": ["self:dom_tags", "hr:dom_depth"],
        "response_speed": ["self:speed_case", "hr:speed_probe"],
        "stability": ["assessment:leveling.grade"],
        "collaboration_compliance": ["assessment:status"],
    }
    return {
        "schema_version": "candidate_assessment_report_v1",
        "executive_summary": "Synthetic evidence supports a governed review.",
        "recommendation": {
            "decision": "PROCEED_WITH_VALIDATION",
            "rationale": ["Synthetic evidence requires human validation."],
        },
        "level_and_pay": {
            "recommended_grade": "C1",
            "salary_band": {"p25": 18000, "p50": 20000, "p75": 23000},
            "confidence": "MEDIUM",
            "interpretation": "The deterministic band is retained unchanged.",
        },
        "dimensions": [
            {
                "dimension": dimension,
                "finding": f"Synthetic {dimension} evidence is available.",
                "confidence": "MEDIUM",
                "evidence_refs": evidence[dimension],
            }
            for dimension in dimensions
        ],
        "agreement_and_conflicts": [],
        "risks_and_evidence_gaps": [],
        "follow_up_questions": ["Validate the synthetic evidence with a human."],
        "onboarding_validation": [],
        "limitations": [
            "Decision support only; not an automatic employment decision."
        ],
        "source_snapshot_hash": snapshot_hash,
    }


def candidate_assessment_contract_fixture() -> dict:
    """Generate a sanitized contract through the real stdlib stores."""

    cid = "c20260907090000abcd"
    workflow_id = "wf_candidate_contract_001"
    template = default_template()
    template_version = template["version"]
    self_assess = {
        "answers": {
            "dom_tags": ["oncology"],
            "perf_amount": 90,
            "speed_case": "same-day mapping",
        },
        "scored": {
            "claimed_billing_wan": 90.0,
            "dimensions": {
                dimension: {"answers": {}, "score": 4.0}
                for dimension in DIM_IDS
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
                dimension: {"answers": {}, "score": 4.0}
                for dimension in DIM_IDS
            },
            "domain_tags": [],
            "redline": False,
            "role": "hr",
            "template_version": template_version,
        },
        "submitted_at": "2026-09-07T09:20:00+00:00",
    }

    original_store_root = candidate_store.CANDIDATES_DIR
    original_report_root = candidate_report_store.CANDIDATES_DIR
    with TemporaryDirectory(prefix="candidate-contract-") as temporary:
        candidates_root = os.path.join(temporary, "candidates")
        candidate_store.CANDIDATES_DIR = candidates_root
        candidate_report_store.CANDIDATES_DIR = candidates_root
        try:
            candidate_store.save_json(
                cid,
                "profile.json",
                {
                    "cid": cid,
                    "name": "Synthetic Candidate",
                    "target_line": "oncology",
                    "notes": "Synthetic contract data only",
                    "created_at": "2026-09-07T09:00:00+00:00",
                    "token": "private-expired-token",
                    "token_expires_at": "2026-09-07T08:00:00+00:00",
                    "hr_token": "private-hr-token",
                    "hr_token_expires_at": "2026-09-14T09:00:00+00:00",
                    "self_submitted_at": None,
                    "hr_submitted_at": None,
                    "assessed_at": None,
                    "status": "CREATED",
                },
            )
            rotation = candidate_store.rotate_questionnaire_token(
                cid,
                "self",
                now=datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
            )
            candidate_store.save_json(cid, "self_assess.json", self_assess)
            candidate_store.save_json(cid, "hr_assess.json", hr_assess)
            candidate_store.update(
                cid,
                self_submitted_at=self_assess["submitted_at"],
                hr_submitted_at=hr_assess["submitted_at"],
                assessed_at="2026-09-07T09:30:00+00:00",
                status="ASSESSED",
            )
            facts = candidate_store.candidate_workflow_facts(cid)
            source_versions = facts["source_versions"]
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
            candidate_store.save_json(
                cid, f"assessment_{assessment_version_id}.json", assessment
            )
            candidate_store.update(
                cid, latest_assessment_version_id=assessment_version_id
            )
            profile = candidate_store.get(cid)
            assert profile is not None
            detail = {
                "completion": facts["completion"],
                "hr_assess": hr_assess,
                "latest_assessment": assessment,
                "latest_assessment_version_id": assessment_version_id,
                "profile": profile,
                "questionnaire": {
                    **facts["questionnaire"],
                    "template_id": template["template_id"],
                    "template_version": template_version,
                },
                "self_assess": self_assess,
                "source_versions": source_versions,
            }
            snapshot_without_hash = {
                "candidate": {
                    "name": profile["name"],
                    "notes": profile["notes"],
                    "target_line": profile["target_line"],
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
                    "template_id": template["template_id"],
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
                + hashlib.sha256(
                    f"{workflow_id}:{input_snapshot_hash}".encode("utf-8")
                ).hexdigest()[:24]
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
                "report": _private_report(input_snapshot_hash),
                "report_id": report_id,
                "report_version": 1,
                "schema_version": "candidate_assessment_report_v1",
                "workflow_id": workflow_id,
                "workflow_run_id": f"{workflow_id}:attempt:1",
            }
            stored = candidate_report_store.archive_report(
                cid, report_artifact, expected_version=1
            )
            reread = candidate_report_store.get_report_version(cid, report_id, 1)
            assert reread == stored
            report_metadata = {
                "artifact_hash": stored["artifact_hash"],
                "assessment_version_id": stored["assessment_version_id"],
                "cid": stored["cid"],
                "input_snapshot_hash": stored["input_snapshot_hash"],
                "report_id": stored["report_id"],
                "report_schema_version": stored["schema_version"],
                "report_version": stored["report_version"],
                "response_shape": sorted(stored),
                "workflow_id": stored["workflow_id"],
            }
        finally:
            candidate_store.CANDIDATES_DIR = original_store_root
            candidate_report_store.CANDIDATES_DIR = original_report_root

    dimension_ids = list(DIM_IDS)
    return {
        "assessment_metadata": {
            "assessment_version_id": assessment_version_id,
            "cid": cid,
            "source_versions": source_versions,
            "template_id": "consultant_v1",
            "template_version": template_version,
            "dimension_ids": dimension_ids,
        },
        "candidate_detail": {
            "completion": facts["completion"],
            "latest_assessment": {
                "assessment_version_id": assessment_version_id,
                "dimension_ids": dimension_ids,
                "source_versions": source_versions,
                "status": assessment["status"],
                "template_version": template_version,
            },
            "latest_assessment_version_id": assessment_version_id,
            "profile": {
                "cid": cid,
                "latest_assessment_version_id": assessment_version_id,
                "name": profile["name"],
                "status": profile["status"],
            },
            "questionnaire": {
                "template_id": template["template_id"],
                "template_version": template_version,
            },
            "response_shape": sorted(detail),
            "responses": {
                "hr": {
                    "dimension_ids": dimension_ids,
                    "present": True,
                    "role": "hr",
                    "source_version": source_versions["hr"],
                    "template_version": template_version,
                },
                "self": {
                    "dimension_ids": dimension_ids,
                    "present": True,
                    "role": "self",
                    "source_version": source_versions["self"],
                    "template_version": template_version,
                },
            },
            "source_versions": source_versions,
        },
        "questionnaire_token_rotation": {
            "cid": cid,
            "expires_at": rotation["expires_at"],
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

    def reject_response_bodies(value: object) -> None:
        if isinstance(value, dict):
            forbidden_body_keys = {"answers", "scored", "report"} & set(value)
            assert not forbidden_body_keys, forbidden_body_keys
            for child in value.values():
                reject_response_bodies(child)
        elif isinstance(value, list):
            for child in value:
                reject_response_bodies(child)

    reject_response_bodies(payload)


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

from fastapi.testclient import TestClient
TMP = os.environ["HEADHUNT_DATA_DIR"]
from api.main import app

client = TestClient(app)

SELF = {"perf_amount": 90, "perf_max_deal": 25, "perf_desc": "某CDMO管线总监单，客户续约二期",
        "dom_tags": ["医学", "临床运营"], "dom_share": "医学70% 临床运营30%",
        "speed_jc": "1-2天", "speed_case": "接到JC当天出mapping次日首推",
        "stab_moves": "1次", "stab_reason": "原平台团队解散", "comp_share": "按规则分单"}
HR = {"perf_verify": "有部分佐证，数字合理", "perf_probe": "基本自洽，个别含糊",
      "dom_depth": "领域知识扎实", "speed_probe": "路径可行",
      "stab_verify": "基本可信", "comp_redline": "拒绝，边界感一般"}


def test_e2e_full_flow():
    r = client.post("/api/candidate/intake",
                    json={"name": "e2e测试候选人", "target_line": "医学线", "notes": "e2e"}).json()
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
    assert out["line_match"]["top_line"] in ("医学线", "临床运营线")

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
    assert payload["assessment_metadata"]["dimension_ids"] == [
        "performance",
        "domain",
        "speed",
        "stability",
        "compliance",
    ]


if __name__ == "__main__":
    for n, f in sorted(list(globals().items())):
        if n.startswith("test_"):
            f(); print(n, "PASS")
