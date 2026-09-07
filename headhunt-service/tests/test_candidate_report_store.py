"""Immutable candidate assessment report artifact storage."""

from __future__ import annotations

import importlib

import pytest

from candidate import store


def _report_store():
    try:
        return importlib.import_module("candidate.report_store")
    except ModuleNotFoundError:
        pytest.fail("candidate.report_store is not implemented")


def _artifact(cid: str, *, version: int = 1, summary: str = "建议进入复核") -> dict:
    return {
        "schema_version": "candidate_assessment_report_v1",
        "report_id": "car_example_001",
        "report_version": version,
        "cid": cid,
        "workflow_id": "wf_example_001",
        "workflow_run_id": f"wfr_example_{version:03d}",
        "input_snapshot_hash": "sha256:" + "a" * 64,
        "assessment_version_id": "cav_" + "b" * 24,
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
            "executive_summary": summary,
            "source_snapshot_hash": "sha256:" + "a" * 64,
        },
    }


def test_archive_is_idempotent_and_rejects_same_version_overwrite() -> None:
    reports = _report_store()
    rec = store.new_candidate("报告存档")
    artifact = _artifact(rec["cid"])

    first = reports.archive_report(rec["cid"], artifact, expected_version=1)
    replay = reports.archive_report(rec["cid"], artifact, expected_version=1)

    assert replay == first
    assert first["artifact_hash"].startswith("sha256:")
    assert reports.get_report_version(rec["cid"], "car_example_001", 1) == first

    changed = _artifact(rec["cid"], summary="被篡改的结论")
    with pytest.raises(reports.ReportStoreError, match="report_version_conflict"):
        reports.archive_report(rec["cid"], changed, expected_version=1)


def test_archive_requires_exact_candidate_and_sequential_version() -> None:
    reports = _report_store()
    rec = store.new_candidate("版本顺序")

    mismatched = _artifact("c999999999999999999")
    with pytest.raises(reports.ReportStoreError, match="report_identity_mismatch"):
        reports.archive_report(rec["cid"], mismatched, expected_version=1)

    version_two = _artifact(rec["cid"], version=2)
    with pytest.raises(reports.ReportStoreError, match="report_previous_version_missing"):
        reports.archive_report(rec["cid"], version_two, expected_version=2)


def test_archive_rejects_version_and_snapshot_mismatch() -> None:
    reports = _report_store()
    rec = store.new_candidate("哈希边界")

    with pytest.raises(reports.ReportStoreError, match="report_version_mismatch"):
        reports.archive_report(rec["cid"], _artifact(rec["cid"]), expected_version=2)

    artifact = _artifact(rec["cid"])
    artifact["report"]["source_snapshot_hash"] = "sha256:" + "c" * 64
    with pytest.raises(reports.ReportStoreError, match="report_snapshot_mismatch"):
        reports.archive_report(rec["cid"], artifact, expected_version=1)


def test_read_rejects_invalid_identifiers_and_missing_artifact() -> None:
    reports = _report_store()
    rec = store.new_candidate("读取边界")

    with pytest.raises(reports.ReportStoreError, match="report_id_invalid"):
        reports.get_report_version(rec["cid"], "../escape", 1)
    with pytest.raises(reports.ReportStoreError, match="report_version_invalid"):
        reports.get_report_version(rec["cid"], "car_example_001", 0)
    with pytest.raises(reports.ReportStoreError, match="report_not_found"):
        reports.get_report_version(rec["cid"], "car_example_001", 1)
