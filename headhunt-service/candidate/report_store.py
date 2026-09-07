# -*- coding: utf-8 -*-
"""Immutable report artifacts for external candidate assessments."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from typing import Any

from candidate.store import CANDIDATES_DIR, get as get_candidate


REPORT_SCHEMA_VERSION = "candidate_assessment_report_v1"
_REPORT_ID_RE = re.compile(r"^car_[A-Za-z0-9_-]{4,64}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ReportStoreError(ValueError):
    """Stable storage-contract failure code."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _artifact_hash(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _validate_report_id(report_id: str) -> None:
    if not _REPORT_ID_RE.fullmatch(str(report_id or "")):
        raise ReportStoreError("report_id_invalid")


def _validate_version(version: int) -> None:
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ReportStoreError("report_version_invalid")


def _reports_root(cid: str) -> str:
    if get_candidate(cid) is None:
        raise ReportStoreError("candidate_not_found")
    return os.path.join(CANDIDATES_DIR, cid, "reports")


def _report_path(cid: str, report_id: str, version: int) -> str:
    _validate_report_id(report_id)
    _validate_version(version)
    return os.path.join(_reports_root(cid), report_id, f"v{version:04d}.json")


def _read(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ReportStoreError("report_artifact_invalid")
    return payload


def _atomic_write(path: str, payload: Mapping[str, Any]) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".report-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=1, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _validate_artifact(cid: str, artifact: Mapping[str, Any], expected_version: int) -> None:
    _validate_version(expected_version)
    if artifact.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ReportStoreError("report_schema_version_invalid")
    if artifact.get("cid") != cid:
        raise ReportStoreError("report_identity_mismatch")
    report_id = str(artifact.get("report_id") or "")
    _validate_report_id(report_id)
    version = artifact.get("report_version")
    _validate_version(version)
    if version != expected_version:
        raise ReportStoreError("report_version_mismatch")
    snapshot_hash = artifact.get("input_snapshot_hash")
    if not isinstance(snapshot_hash, str) or not _HASH_RE.fullmatch(snapshot_hash):
        raise ReportStoreError("report_snapshot_hash_invalid")
    report = artifact.get("report")
    if not isinstance(report, Mapping):
        raise ReportStoreError("report_payload_invalid")
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ReportStoreError("report_schema_version_invalid")
    if report.get("source_snapshot_hash") != snapshot_hash:
        raise ReportStoreError("report_snapshot_mismatch")


def archive_report(
    cid: str,
    artifact: Mapping[str, Any],
    *,
    expected_version: int,
) -> dict[str, Any]:
    """Atomically create one report version or replay identical content."""
    _validate_artifact(cid, artifact, expected_version)
    report_id = str(artifact["report_id"])
    path = _report_path(cid, report_id, expected_version)
    stored = dict(artifact)
    stored["artifact_hash"] = _artifact_hash(artifact)
    if os.path.exists(path):
        existing = _read(path)
        if existing == stored:
            return existing
        raise ReportStoreError("report_version_conflict")
    if expected_version > 1:
        previous = _report_path(cid, report_id, expected_version - 1)
        if not os.path.isfile(previous):
            raise ReportStoreError("report_previous_version_missing")
    _atomic_write(path, stored)
    return stored


def get_report_version(cid: str, report_id: str, version: int) -> dict[str, Any]:
    """Read one exact immutable report version."""
    path = _report_path(cid, report_id, version)
    if not os.path.isfile(path):
        raise ReportStoreError("report_not_found")
    return _read(path)
