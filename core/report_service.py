from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Template

from .candidate_brief import CandidateBriefStore
from .config_loader import get_loader
from .hiijob_agent import HiijobAgentClient
from .html_renderer import write_report_html
from .pdf_renderer import PdfReportRenderer
from .redactor import privacy_redact
from .renderer import ReportRenderer
from .resume_parser import parse_resume_for_report
from .validator import DataValidator

DEFAULT_PUBLIC_BASE_URL = "http://localhost:8810"


REPORT_UPDATE_FIELDS = {
    "brand_id",
    "candidate_name",
    "position_title",
    "current_company",
    "current_title",
    "client_company",
    "salary_info",
    "job_description",
    "report_style",
    "motivation",
    "role_fit",
    "resume_text",
    "original_resume",
    "resume_source_id",
    "candidate_brief_id",
    "candidate_brief",
    "professional_photo_data_uri",
    "professional_photo_file_name",
    "professional_photo_required",
}

RATIONALE_UPDATE_FIELDS = {
    "strengths_summary",
    "risk_notes",
    "recommendation_rationale",
}


class ReportService:
    def __init__(
        self,
        config_dir: str | Path | None = None,
        data_dir: str | Path | None = None,
        public_base_url: str = DEFAULT_PUBLIC_BASE_URL,
        agent_client: HiijobAgentClient | None = None,
    ) -> None:
        self.loader = get_loader(config_dir)
        self.data_dir = Path(data_dir or Path(__file__).parent.parent / "data")
        self.public_base_url = public_base_url.rstrip("/")
        self.agent_client = agent_client or HiijobAgentClient.from_env()
        self.brief_store = CandidateBriefStore(self.data_dir)
        self.drafts_dir = self.data_dir / "drafts"
        self.outputs_dir = self.data_dir / "outputs"
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def create_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        brand_id = payload.get("brand_id") or "default"
        brand_config = self.loader.load_brand(brand_id)
        data = dict(payload)
        data["brand_id"] = brand_id
        data["report_style"] = self._normalize_report_style(data.get("report_style"))
        if data.get("resume_text") and not data.get("original_resume"):
            data["original_resume"] = data["resume_text"]
        self._materialize_candidate_brief(data)
        privacy_rules = brand_config.get("compliance", {}).get("privacy_rules")
        if data.get("original_resume") and privacy_rules:
            data["original_resume"] = privacy_redact(data["original_resume"], privacy_rules)
        if not data.get("parsed_resume") and ("original_resume" in data or "resume_text" in data):
            self._parse_resume_into_data(data, str(data.get("original_resume") or data.get("resume_text") or ""))

        validator = DataValidator(brand_config)
        validation = validator.validate(data)
        report_id = data.get("report_id") or f"report_{uuid.uuid4().hex}"
        now = datetime.now(UTC).isoformat()
        record = {
            "report_id": report_id,
            "brand_id": brand_id,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
            "data": data,
            "validation": validation.to_dict(),
        }
        self._save_record(record)
        return self._response_for(record)

    def generate_comments(self, report_id: str, feedback: str = "") -> dict[str, Any]:
        record = self._load_record(report_id)
        self._refresh_parsed_resume(record)
        context = dict(record["data"])
        if feedback:
            context["feedback"] = feedback
        result = self.agent_client.generate_comments(context)
        comments = result.get("comments", {})
        record["data"].update(comments)
        record["ai_missing_information"] = result.get("missing_information", [])
        record["updated_at"] = datetime.now(UTC).isoformat()
        brand_config = self.loader.load_brand(record["brand_id"])
        validation = DataValidator(brand_config).validate(record["data"])
        record["validation"] = validation.to_dict()
        self._save_record(record)
        # 返回包含 data 字段的完整响应，供前端填充表单
        return {
            "report_id": report_id,
            "data": record["data"],
            "validation": record["validation"],
            "status": record["status"],
            "missing_information": record["validation"].get("missing_items", []),
        }

    def render_report(self, report_id: str) -> dict[str, Any]:
        record = self._load_record(report_id)
        self._refresh_parsed_resume(record)
        brand_config = self.loader.load_brand(record["brand_id"])
        data = DataValidator(brand_config).prepare_draft_payload(record["data"])
        filename = self._filename(brand_config, data, "docx")
        output_path = self.outputs_dir / filename
        ReportRenderer(brand_config, None).render(data, output_path)
        validation = DataValidator(brand_config).validate(record["data"])
        record["status"] = "confirmed" if validation.is_valid else "draft"
        record["validation"] = validation.to_dict()
        record["output"] = {"filename": filename}
        record["updated_at"] = datetime.now(UTC).isoformat()
        self._save_record(record)
        return {
            "report_id": report_id,
            "status": record["status"],
            "filename": filename,
            "download_url": f"{self.public_base_url}/downloads/{filename}",
            "missing_information": record["validation"].get("missing_items", []),
        }

    def update_report(
        self,
        report_id: str,
        known_fields: dict[str, Any],
        feedback: str = "",
    ) -> dict[str, Any]:
        record = self._load_record(report_id)
        data = record.setdefault("data", {})
        updated_fields: dict[str, Any] = {}
        ignored_fields: list[str] = []

        for key, value in (known_fields or {}).items():
            if value is None:
                continue
            if key in REPORT_UPDATE_FIELDS:
                normalized = self._normalize_update_value(key, value)
                data[key] = normalized
                updated_fields[key] = normalized
            elif key in RATIONALE_UPDATE_FIELDS:
                rationale = data.setdefault("recommendation_rationale", {})
                if key == "recommendation_rationale" and isinstance(value, dict):
                    for nested_key, nested_value in value.items():
                        if nested_key in {"strengths_summary", "risk_notes"} and nested_value is not None:
                            rationale[nested_key] = str(nested_value).strip()
                            updated_fields[f"recommendation_rationale.{nested_key}"] = rationale[nested_key]
                elif key in {"strengths_summary", "risk_notes"}:
                    rationale[key] = str(value).strip()
                    updated_fields[f"recommendation_rationale.{key}"] = rationale[key]
            else:
                ignored_fields.append(key)

        if feedback:
            notes = data.setdefault("conversation_feedback", [])
            notes.append(
                {
                    "at": datetime.now(UTC).isoformat(),
                    "feedback": str(feedback).strip(),
                }
            )

        if "report_style" in updated_fields:
            data["report_style"] = self._normalize_report_style(data.get("report_style"))
            updated_fields["report_style"] = data["report_style"]

        if "resume_text" in updated_fields and not data.get("original_resume"):
            data["original_resume"] = data["resume_text"]
            updated_fields["original_resume"] = data["original_resume"]

        if "original_resume" in updated_fields or "resume_text" in updated_fields:
            self._materialize_candidate_brief(data)
            resume_source = data.get("original_resume") or data.get("resume_text") or ""
            self._parse_resume_into_data(data, str(resume_source))
            updated_fields["parsed_resume"] = data["parsed_resume"]
            updated_fields["resume_quality"] = data.get("resume_quality")
            updated_fields["resume_source_id"] = data.get("resume_source_id")
            updated_fields["candidate_brief_id"] = data.get("candidate_brief_id")

        if "resume_source_id" in updated_fields or "candidate_brief_id" in updated_fields:
            self._materialize_candidate_brief(data)
            resume_source = data.get("original_resume") or data.get("resume_text") or ""
            if resume_source:
                self._parse_resume_into_data(data, str(resume_source))
                updated_fields["parsed_resume"] = data["parsed_resume"]
                updated_fields["resume_quality"] = data.get("resume_quality")

        brand_config = self.loader.load_brand(data.get("brand_id") or record["brand_id"])
        validation = DataValidator(brand_config).validate(data)
        record["brand_id"] = data.get("brand_id") or record["brand_id"]
        record["validation"] = validation.to_dict()
        record["updated_at"] = datetime.now(UTC).isoformat()
        self._save_record(record)

        response = self._response_for(record)
        response["updated_fields"] = updated_fields
        response["ignored_fields"] = ignored_fields
        return response

    def render_html_report(self, report_id: str) -> dict[str, Any]:
        record = self._load_record(report_id)
        self._refresh_parsed_resume(record)
        brand_config = self.loader.load_brand(record["brand_id"])
        data = DataValidator(brand_config).prepare_draft_payload(record["data"])
        filename = self._filename(brand_config, data, "html")
        output_path = self.outputs_dir / filename
        write_report_html(data, brand_config, output_path)
        record["output_html"] = {"filename": filename}
        record["updated_at"] = datetime.now(UTC).isoformat()
        self._save_record(record)
        return {
            "report_id": report_id,
            "status": record.get("status", "draft"),
            "filename": filename,
            "download_url": f"{self.public_base_url}/downloads/{filename}",
        }

    def render_pdf_report(self, report_id: str) -> dict[str, Any]:
        record = self._load_record(report_id)
        self._refresh_parsed_resume(record)
        brand_config = self.loader.load_brand(record["brand_id"])
        data = DataValidator(brand_config).prepare_draft_payload(record["data"])
        filename = self._filename(brand_config, data, "pdf")
        output_path = self.outputs_dir / filename
        PdfReportRenderer(brand_config).render(data, output_path)
        record["output_pdf"] = {"filename": filename}
        record["updated_at"] = datetime.now(UTC).isoformat()
        self._save_record(record)
        return {
            "report_id": report_id,
            "status": record.get("status", "draft"),
            "filename": filename,
            "download_url": f"{self.public_base_url}/downloads/{filename}",
        }

    def card_context(self, report_id: str) -> dict[str, Any]:
        record = self._load_record(report_id)
        self._refresh_parsed_resume(record)
        brand_config = self.loader.load_brand(record["brand_id"])
        return {
            "report": record,
            "data": record.get("data", {}),
            "validation": record.get("validation", {}),
            "render_url": f"{self.public_base_url}/api/v1/reports/{report_id}/render",
            "template_diagnostics": self._template_diagnostics(brand_config),
        }

    def render_card_html(self, report_id: str) -> str:
        template_path = Path(__file__).parent.parent / "cards" / "report_review.html"
        template = Template(template_path.read_text(encoding="utf-8"))
        return template.render(**self.card_context(report_id))

    def output_path(self, filename: str) -> Path:
        safe_name = Path(filename).name
        path = self.outputs_dir / safe_name
        if not path.exists():
            raise FileNotFoundError(safe_name)
        return path

    def _response_for(self, record: dict[str, Any]) -> dict[str, Any]:
        report_id = record["report_id"]
        return {
            "report_id": report_id,
            "status": record.get("status", "draft"),
            "data": record.get("data", {}),
            "validation": record.get("validation", {}),
            "card_url": f"{self.public_base_url}/cards/reports/{report_id}",
            "render_url": f"{self.public_base_url}/api/v1/reports/{report_id}/render",
            "missing_information": record.get("validation", {}).get("missing_items", []),
        }

    def _record_path(self, report_id: str) -> Path:
        if not re.match(r"^report_[a-f0-9]+$", report_id):
            raise ValueError("Invalid report_id")
        return self.drafts_dir / f"{report_id}.json"

    def _load_record(self, report_id: str) -> dict[str, Any]:
        path = self._record_path(report_id)
        if not path.exists():
            raise FileNotFoundError(report_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_record(self, record: dict[str, Any]) -> None:
        path = self._record_path(record["report_id"])
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def _refresh_parsed_resume(self, record: dict[str, Any]) -> bool:
        data = record.setdefault("data", {})
        before_ids = (data.get("resume_source_id"), data.get("candidate_brief_id"))
        materialized = self._materialize_candidate_brief(data)
        resume_source = str(data.get("original_resume") or data.get("resume_text") or "").strip()
        if not resume_source:
            return False
        parsed = parse_resume_for_report(resume_source)
        if data.get("parsed_resume") == parsed and not materialized and before_ids == (
            data.get("resume_source_id"),
            data.get("candidate_brief_id"),
        ):
            return False
        data["parsed_resume"] = parsed
        data["resume_quality"] = parsed.get("quality", {})
        record["updated_at"] = datetime.now(UTC).isoformat()
        return True

    def _parse_resume_into_data(self, data: dict[str, Any], resume_source: str) -> None:
        parsed = parse_resume_for_report(str(resume_source or ""))
        data["parsed_resume"] = parsed
        data["resume_quality"] = parsed.get("quality", {})

    def create_resume_source(self, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.brief_store.create_resume_source(text, metadata=metadata)

    def create_candidate_brief(
        self,
        resume_source_id: str,
        known_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.brief_store.create_candidate_brief(resume_source_id, known_fields=known_fields)

    def get_candidate_brief(self, candidate_brief_id: str) -> dict[str, Any]:
        return self.brief_store.load_candidate_brief(candidate_brief_id)

    def _materialize_candidate_brief(self, data: dict[str, Any]) -> bool:
        before = (
            data.get("resume_source_id"),
            data.get("candidate_brief_id"),
            bool(data.get("candidate_brief")),
            str(data.get("original_resume") or data.get("resume_text") or ""),
        )

        brief_id = str(data.get("candidate_brief_id") or "").strip()
        if brief_id:
            brief = self.brief_store.load_candidate_brief(brief_id)
            source = self.brief_store.load_resume_source(str(brief["resume_source_id"]))
            data["candidate_brief"] = brief
            data["candidate_brief_id"] = brief["candidate_brief_id"]
            data["resume_source_id"] = brief["resume_source_id"]
            data["original_resume"] = source.get("text", "")
            data.setdefault("resume_text", source.get("text", ""))
            self._apply_candidate_brief_defaults(data, brief)
            return before != (
                data.get("resume_source_id"),
                data.get("candidate_brief_id"),
                bool(data.get("candidate_brief")),
                str(data.get("original_resume") or data.get("resume_text") or ""),
            )

        source_id = str(data.get("resume_source_id") or "").strip()
        if source_id:
            source = self.brief_store.load_resume_source(source_id)
            data["resume_source_id"] = source["resume_source_id"]
            data["original_resume"] = source.get("text", "")
            data.setdefault("resume_text", source.get("text", ""))

        resume_source = str(data.get("original_resume") or data.get("resume_text") or "").strip()
        if not resume_source:
            return False

        metadata = {
            "file_name": data.get("resume_file_name", ""),
            "report_id": data.get("report_id", ""),
        }
        source = self.brief_store.create_resume_source(resume_source, metadata=metadata)
        data["resume_source_id"] = source["resume_source_id"]
        known_fields = self._brief_known_fields(data)
        brief = self.brief_store.create_candidate_brief(source["resume_source_id"], known_fields=known_fields)
        data["candidate_brief_id"] = brief["candidate_brief_id"]
        data["candidate_brief"] = brief
        data["original_resume"] = source.get("text", resume_source)
        data.setdefault("resume_text", source.get("text", resume_source))
        self._apply_candidate_brief_defaults(data, brief)
        return before != (
            data.get("resume_source_id"),
            data.get("candidate_brief_id"),
            bool(data.get("candidate_brief")),
            str(data.get("original_resume") or data.get("resume_text") or ""),
        )

    def _apply_candidate_brief_defaults(self, data: dict[str, Any], brief: dict[str, Any]) -> None:
        identity = brief.get("identity") if isinstance(brief.get("identity"), dict) else {}
        intent = brief.get("intent") if isinstance(brief.get("intent"), dict) else {}
        compensation = brief.get("compensation") if isinstance(brief.get("compensation"), dict) else {}
        defaults = {
            "candidate_name": identity.get("candidate_name"),
            "current_company": identity.get("current_company"),
            "current_title": identity.get("current_title"),
            "position_title": intent.get("target_role"),
            "client_company": intent.get("client_company"),
            "job_description": intent.get("job_description"),
            "salary_info": compensation.get("salary_info"),
        }
        for key, value in defaults.items():
            if data.get(key) in {None, ""} and value not in {None, ""}:
                data[key] = value

    def _brief_known_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        keys = {
            "brand_id",
            "candidate_name",
            "position_title",
            "current_company",
            "current_title",
            "client_company",
            "salary_info",
            "job_description",
            "report_style",
        }
        return {key: data.get(key) for key in keys if data.get(key) not in {None, ""}}

    def _filename(self, brand_config: dict[str, Any], data: dict[str, Any], extension: str = "docx") -> str:
        export = brand_config.get("export", {})
        template = export.get("filename_template", "{brand_id}_{candidate_name}_report_{date}")
        raw = template.format(
            brand_id=brand_config.get("brand_id", "default"),
            candidate_name=data.get("candidate_name", "candidate"),
            date=datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")
        return f"{safe}.{extension.lstrip('.')}"

    def _normalize_report_style(self, value: Any) -> str:
        style = str(value or "tstar_warm").strip()
        return style if style in {"tstar_warm", "consulting_blue"} else "tstar_warm"

    def _normalize_update_value(self, key: str, value: Any) -> Any:
        if key == "report_style":
            return self._normalize_report_style(value)
        if key == "brand_id":
            return str(value or "tstar").strip() or "tstar"
        if isinstance(value, str):
            return value.strip()
        return value

    def _template_diagnostics(self, brand_config: dict[str, Any]) -> dict[str, Any]:
        mapping = brand_config.get("template_mapping", {})
        references = mapping.get("reference_templates", {})
        return {
            "docx_mode": "client_template" if mapping.get("use_client_template") else "programmatic",
            "uses_client_template": bool(mapping.get("use_client_template")),
            "client_template_path": mapping.get("client_template_path", ""),
            "reference_templates": references if isinstance(references, dict) else {},
            "message": (
                "DOCX currently uses a programmatic renderer. Registered Chinese/English templates are references only."
                if not mapping.get("use_client_template")
                else "DOCX client template mode is enabled."
            ),
        }
