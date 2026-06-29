from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Template

from .config_loader import get_loader
from .hiijob_agent import HiijobAgentClient
from .redactor import privacy_redact
from .renderer import ReportRenderer
from .validator import DataValidator

DEFAULT_PUBLIC_BASE_URL = "http://localhost:8810"


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
        self.drafts_dir = self.data_dir / "drafts"
        self.outputs_dir = self.data_dir / "outputs"
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def create_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        brand_id = payload.get("brand_id") or "default"
        brand_config = self.loader.load_brand(brand_id)
        data = dict(payload)
        data["brand_id"] = brand_id
        if data.get("resume_text") and not data.get("original_resume"):
            data["original_resume"] = data["resume_text"]
        privacy_rules = brand_config.get("compliance", {}).get("privacy_rules")
        if data.get("original_resume") and privacy_rules:
            data["original_resume"] = privacy_redact(data["original_resume"], privacy_rules)

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
        return self._response_for(record)

    def render_report(self, report_id: str) -> dict[str, Any]:
        record = self._load_record(report_id)
        brand_config = self.loader.load_brand(record["brand_id"])
        data = DataValidator(brand_config).prepare_draft_payload(record["data"])
        filename = self._filename(brand_config, data)
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

    def card_context(self, report_id: str) -> dict[str, Any]:
        record = self._load_record(report_id)
        return {
            "report": record,
            "data": record.get("data", {}),
            "validation": record.get("validation", {}),
            "render_url": f"{self.public_base_url}/api/v1/reports/{report_id}/render",
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

    def _filename(self, brand_config: dict[str, Any], data: dict[str, Any]) -> str:
        export = brand_config.get("export", {})
        template = export.get("filename_template", "{brand_id}_{candidate_name}_report_{date}")
        raw = template.format(
            brand_id=brand_config.get("brand_id", "default"),
            candidate_name=data.get("candidate_name", "candidate"),
            date=datetime.now().strftime("%Y%m%d"),
        )
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")
        return f"{safe}.docx"
