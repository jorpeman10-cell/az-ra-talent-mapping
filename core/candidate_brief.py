from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .placeholder_report import build_placeholder_context
from .resume_parser import parse_resume_for_report


RESUME_SOURCE_RE = re.compile(r"^rs_[a-f0-9]{32}$")
CANDIDATE_BRIEF_RE = re.compile(r"^cb_[a-f0-9]{32}$")
SCHEMA_VERSION = "2026-07-10.1"


class ResumeQualityError(ValueError):
    def __init__(self, quality: dict[str, Any]) -> None:
        super().__init__("Resume text quality is insufficient for candidate brief generation")
        self.quality = quality

    def to_detail(self) -> dict[str, Any]:
        return {
            "code": "resume_quality_blocked",
            "message": str(self),
            "quality": self.quality,
            "next_action": "upload_text_resume_or_run_ocr",
        }


class CandidateBriefStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.resume_sources_dir = self.data_dir / "resume_sources"
        self.candidate_briefs_dir = self.data_dir / "candidate_briefs"
        self.resume_sources_dir.mkdir(parents=True, exist_ok=True)
        self.candidate_briefs_dir.mkdir(parents=True, exist_ok=True)

    def create_resume_source(self, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        value = str(text or "").strip()
        if not value:
            raise ValueError("Resume source text is required")
        content_hash = hashlib.sha256(value.encode("utf-8")).hexdigest()
        source_id = f"rs_{content_hash[:32]}"
        path = self._resume_source_path(source_id)
        payload = {
            "resume_source_id": source_id,
            "schema_version": SCHEMA_VERSION,
            "content_hash": content_hash,
            "char_count": len(value),
            "text": value,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing["metadata"] = {**existing.get("metadata", {}), **(metadata or {})}
            path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            return existing
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def load_resume_source(self, source_id: str) -> dict[str, Any]:
        path = self._resume_source_path(source_id)
        if not path.exists():
            raise FileNotFoundError(source_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def create_candidate_brief(
        self,
        resume_source_id: str,
        known_fields: dict[str, Any] | None = None,
        require_publishable: bool = False,
    ) -> dict[str, Any]:
        source = self.load_resume_source(resume_source_id)
        fields = _compact_dict(known_fields or {})
        resume_text = str(source.get("text") or "")
        parsed = parse_resume_for_report(resume_text)
        if require_publishable:
            _ensure_publishable_resume(parsed)
        stable_payload = json.dumps(
            {
                "resume_source_id": resume_source_id,
                "known_fields": fields,
                "schema_version": SCHEMA_VERSION,
                "quality_gate": "publishable" if require_publishable else "draft",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        brief_id = f"cb_{hashlib.sha256(stable_payload.encode('utf-8')).hexdigest()[:32]}"
        path = self._candidate_brief_path(brief_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

        context_data = {
            **fields,
            "original_resume": resume_text,
            "resume_text": resume_text,
            "parsed_resume": parsed,
        }
        context = build_placeholder_context(context_data, {"brand_id": str(fields.get("brand_id") or "tstar")})
        brief = {
            "candidate_brief_id": brief_id,
            "resume_source_id": resume_source_id,
            "schema_version": SCHEMA_VERSION,
            "content_hash": source.get("content_hash"),
            "identity": _identity_from_context(context, fields),
            "career_history": _career_history_from_context(context),
            "projects": list(context.get("appendix_blocks", {}).get("projects") or []),
            "education": list(context.get("appendix_blocks", {}).get("education") or []),
            "compensation": {
                "salary_info": str(fields.get("salary_info") or context.get("salary_info") or "").strip(),
                "source": "consultant_input" if fields.get("salary_info") else "resume",
            },
            "intent": {
                "target_role": str(fields.get("position_title") or context.get("target_role") or "").strip(),
                "client_company": str(fields.get("client_company") or context.get("client_company") or "").strip(),
                "job_description": str(fields.get("job_description") or "").strip(),
            },
            "consultant_notes": [],
            "highlights": _highlights_from_context(context),
            "provenance": {
                "original_resume": {"source": "resume_source", "source_id": resume_source_id},
                "career_history": {"source": "resume_parser", "source_id": resume_source_id},
                "projects": {"source": "resume_parser", "source_id": resume_source_id},
                "education": {"source": "resume_parser", "source_id": resume_source_id},
            },
            "metadata": {
                "source_file_name": source.get("metadata", {}).get("file_name", ""),
                "resume_char_count": source.get("char_count", 0),
                "resume_quality": parsed.get("quality", {}),
                "quality_gate": "publishable" if require_publishable else "draft",
                "created_at": datetime.now(UTC).isoformat(),
            },
        }
        path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
        return brief

    def load_candidate_brief(self, brief_id: str) -> dict[str, Any]:
        path = self._candidate_brief_path(brief_id)
        if not path.exists():
            raise FileNotFoundError(brief_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _resume_source_path(self, source_id: str) -> Path:
        if not RESUME_SOURCE_RE.match(str(source_id or "")):
            raise ValueError("Invalid resume_source_id")
        return self.resume_sources_dir / f"{source_id}.json"

    def _candidate_brief_path(self, brief_id: str) -> Path:
        if not CANDIDATE_BRIEF_RE.match(str(brief_id or "")):
            raise ValueError("Invalid candidate_brief_id")
        return self.candidate_briefs_dir / f"{brief_id}.json"


def _ensure_publishable_resume(parsed: dict[str, Any]) -> None:
    quality = parsed.get("quality") if isinstance(parsed.get("quality"), dict) else {}
    status = str(quality.get("status") or "")
    if status != "ok":
        if not quality:
            quality = {"status": "low_confidence", "reasons": ["missing_quality_assessment"]}
        raise ResumeQualityError(quality)


def _compact_dict(values: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        if value == "":
            continue
        result[key] = value
    return result


def _identity_from_context(context: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    rows = {str(label): str(value) for label, value in context.get("personal_info_rows", [])}
    return {
        "candidate_name": str(fields.get("candidate_name") or context.get("candidate_name") or rows.get("Name / 姓名") or "").strip(),
        "current_company": str(fields.get("current_company") or context.get("current_company") or "").strip(),
        "current_title": str(fields.get("current_title") or context.get("current_title") or "").strip(),
        "phone": _first_row(rows, "Phone / 电话", "电话", "手机", "Phone", "Tel", "Mobile"),
        "email": _first_row(rows, "Email / 邮箱", "邮箱", "电子邮箱", "Email", "E-mail"),
        "location": _first_row(rows, "Address / 地址", "住址", "地址", "Address", "Location"),
    }


def _first_row(rows: dict[str, str], *labels: str) -> str:
    for label in labels:
        value = rows.get(label)
        if value:
            return value
    return ""


def _career_history_from_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for group in context.get("appendix_blocks", {}).get("experience_groups", []) or []:
        company = str(group.get("company") or "").strip()
        roles = []
        for role in group.get("roles", []) or []:
            roles.append({
                "period": str(role.get("period") or "").strip(),
                "title": str(role.get("title") or "").strip(),
                "details": [str(item).strip() for item in role.get("details", []) if str(item).strip()],
            })
        if company or roles:
            history.append({"company": company, "roles": roles})
    return history


def _highlights_from_context(context: dict[str, Any]) -> list[str]:
    highlights: list[str] = []
    for group in context.get("appendix_blocks", {}).get("experience_groups", []) or []:
        for role in group.get("roles", []) or []:
            for detail in role.get("details", []) or []:
                text = str(detail).strip()
                if text:
                    highlights.append(text)
                if len(highlights) >= 12:
                    return highlights
    return highlights
