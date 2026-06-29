# Generic Report Hiijob Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP B9 generic report service with a Hiijob Agent adapter, card review UI, DOCX output, and local debug UI.

**Architecture:** Keep report generation inside `generic-report-tool` as an independent product service. Add a small orchestration layer over the existing core modules, expose FastAPI endpoints, return `card_url` for Hiijob, and keep Streamlit as a debug harness. The Hiijob Agent call is isolated behind an adapter with deterministic fallback.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, python-docx, PyYAML, Jinja2, Streamlit, unittest, requests.

---

## File Structure

- Modify `requirements.txt`: add FastAPI, Uvicorn, and Pydantic for the HTTP service.
- Modify `config/brands/default.yaml`: add the minimal default brand and fields.
- Modify `config/prompts/prompt_engine.yaml`: add the minimal comment-generation prompt.
- Create `core/hiijob_agent.py`: Hiijob Agent adapter and fallback comments.
- Create `core/report_service.py`: draft persistence, validation, comment generation, card data, DOCX rendering.
- Create `api/bridge.py`: FastAPI app and CLI runner.
- Create `cards/report_review.html`: Jinja2 review-card template.
- Create `ui/streamlit_app.py`: local debug UI.
- Create `tests/test_config_and_service.py`: config, validation, fallback, service, render tests.
- Create `tests/test_api_bridge.py`: HTTP endpoint and card tests.
- Modify `docs/superpowers/specs/2026-06-29-generic-report-hiijob-card-design.md` only if implementation reveals a design mismatch.

## Task 1: Contract, Dependencies, And Default Config

**Files:**
- Modify: `requirements.txt`
- Create: `config/brands/default.yaml`
- Create: `config/prompts/prompt_engine.yaml`
- Test: `tests/test_config_and_service.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config_and_service.py` with:

```python
import tempfile
import unittest
from pathlib import Path

from core.config_loader import ConfigValidator, get_loader


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigAndServiceTests(unittest.TestCase):
    def test_default_brand_loads_and_validates(self):
        loader = get_loader(PROJECT_ROOT / "config")
        brand = loader.load_brand("default")
        self.assertEqual(brand["brand_id"], "default")
        self.assertTrue(brand["fields"]["required"])
        validator = ConfigValidator(loader)
        self.assertTrue(validator.validate_brand("default"), validator.errors)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_config_and_service.ConfigAndServiceTests.test_default_brand_loads_and_validates`

Expected: FAIL or ERROR because `config/brands/default.yaml` is missing.

- [ ] **Step 3: Add dependencies**

Update `requirements.txt` to include:

```text
python-docx>=1.1.0
pdfplumber>=0.11.0
PyYAML>=6.0
Jinja2>=3.1.0
streamlit>=1.35.0
requests>=2.31.0
python-dateutil>=2.9.0
fastapi>=0.115.0
uvicorn>=0.30.0
pydantic>=2.7.0
```

- [ ] **Step 4: Add default brand config**

Create `config/brands/default.yaml` with:

```yaml
brand_id: "default"
brand_name: "Generic Referral Report"
version: "1.0.0"
description: "Default generic candidate referral report configuration."

branding:
  primary_color: "#1F6FEB"
  secondary_color: "#2DA44E"
  font_family: "Microsoft YaHei"
  font_family_en: "Arial"

fields:
  required:
    - field: "candidate_name"
      group: "candidate"
      label: "Candidate Name"
      type: "string"
      required: true
    - field: "position_title"
      group: "position"
      label: "Position Title"
      type: "string"
      required: true
    - field: "recommendation_rationale"
      group: "assessment"
      label: "Recommendation Rationale"
      type: "structured_text"
      required: true
      sub_fields:
        - field: "strengths_summary"
          label: "Strengths Summary"
          required: true
        - field: "risk_notes"
          label: "Risk Notes"
          required: false
  optional:
    - field: "current_title"
      group: "candidate"
      label: "Current Title"
      type: "string"
    - field: "current_company"
      group: "candidate"
      label: "Current Company"
      type: "string"
    - field: "location"
      group: "position"
      label: "Location"
      type: "string"
    - field: "job_description"
      group: "position"
      label: "Job Description"
      type: "text"
    - field: "original_resume"
      group: "resume"
      label: "Original Resume"
      type: "text"
  hidden:
    - field: "candidate_consent_confirmed"
      label: "Candidate Consent Confirmed"
      type: "boolean"

comment_style:
  tone: "professional"
  length: "medium"
  language: "zh-en"
  focus_areas:
    - "role fit"
    - "motivation"
    - "career trajectory"

compliance:
  disclaimer:
    enabled: true
    text: "Draft report for consultant review."
  privacy_rules:
    - name: "id_card"
      pattern: "\\b\\d{17}[\\dXx]\\b"
      replacement: "[REDACTED_ID]"

template_mapping:
  use_client_template: false

prompt_rules:
  system_role: "You are a professional executive search consultant drafting a candidate referral report."
  must_follow:
    - "Use only the provided resume, job, and consultant context."
    - "Call out missing information explicitly."
  prohibited:
    - "Do not invent unverifiable facts."

export:
  default_format: "docx"
  filename_template: "{brand_id}_{candidate_name}_report_{date}"
```

- [ ] **Step 5: Add minimal prompt config**

Create `config/prompts/prompt_engine.yaml` with:

```yaml
variables:
  - name: "brand_name"
    source: "brand_config.brand_name"
    default_value: "Generic Referral Report"
  - name: "system_role"
    source: "brand_config.prompt_rules.system_role"
    default_value: "You are a professional executive search consultant."
  - name: "resume_text"
    source: "user_input.resume_text"
    default_value: ""
  - name: "position_title"
    source: "user_input.position_title"
    default_value: ""
  - name: "job_description"
    source: "user_input.job_description"
    default_value: ""

templates:
  - template_id: "generate_draft_comments"
    system_prompt: |
      {{ system_role }}
      Write in a concise, professional, consultant-ready style for {{ brand_name }}.
    user_prompt: |
      Position: {{ position_title }}

      Job Description:
      {{ job_description }}

      Resume:
      {{ resume_text }}

      Return JSON with comments.recommendation_rationale.strengths_summary,
      comments.recommendation_rationale.risk_notes, comments.motivation,
      comments.role_fit, and missing_information.
    output_schema:
      type: "object"
      properties:
        comments:
          type: "object"
        missing_information:
          type: "array"

output_format:
  json_parsing:
    allow_markdown_wrapper: true
    attempt_repair: true
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m unittest tests.test_config_and_service.ConfigAndServiceTests.test_default_brand_loads_and_validates`

Expected: PASS.

## Task 2: Hiijob Agent Adapter

**Files:**
- Create: `core/hiijob_agent.py`
- Modify: `tests/test_config_and_service.py`

- [ ] **Step 1: Write failing fallback test**

Append to `ConfigAndServiceTests`:

```python
    def test_hiijob_agent_fallback_generates_deterministic_comments(self):
        from core.hiijob_agent import HiijobAgentClient

        client = HiijobAgentClient(base_url="", agent_id="", token="")
        result = client.generate_comments({
            "candidate_name": "Alice",
            "position_title": "Medical Director",
            "resume_text": "Alice has oncology and medical affairs experience.",
        })

        comments = result["comments"]
        self.assertIn("recommendation_rationale", comments)
        self.assertIn("Medical Director", comments["role_fit"])
        self.assertTrue(result["missing_information"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_config_and_service.ConfigAndServiceTests.test_hiijob_agent_fallback_generates_deterministic_comments`

Expected: ERROR because `core.hiijob_agent` is missing.

- [ ] **Step 3: Implement adapter**

Create `core/hiijob_agent.py` with:

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class HiijobAgentClient:
    base_url: str | None = None
    agent_id: str | None = None
    token: str | None = None
    timeout: float | None = None

    @classmethod
    def from_env(cls) -> "HiijobAgentClient":
        timeout_raw = os.environ.get("HIIJOB_AGENT_TIMEOUT", "30")
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 30.0
        return cls(
            base_url=os.environ.get("HIIJOB_AGENT_BASE_URL", ""),
            agent_id=os.environ.get("HIIJOB_REPORT_AGENT_ID", ""),
            token=os.environ.get("HIIJOB_AGENT_TOKEN", ""),
            timeout=timeout,
        )

    def generate_comments(self, context: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url or not self.agent_id or not self.token:
            return self._fallback_comments(context)

        payload = {
            "agent_id": self.agent_id,
            "task": "generate_candidate_referral_comments",
            "context": context,
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            self.base_url.rstrip("/") + "/api/v1/agents/run",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            timeout=self.timeout or 30,
        )
        response.raise_for_status()
        data = response.json()
        if "comments" in data:
            return data
        if isinstance(data.get("result"), dict) and "comments" in data["result"]:
            return data["result"]
        return self._fallback_comments(context)

    def _fallback_comments(self, context: dict[str, Any]) -> dict[str, Any]:
        candidate = context.get("candidate_name") or "the candidate"
        position = context.get("position_title") or "the target role"
        resume_text = (context.get("resume_text") or "").strip()
        summary = (
            f"{candidate} appears potentially relevant for {position} based on the provided profile. "
            "Please review and enrich this draft with verified consultant notes."
        )
        if resume_text:
            summary = (
                f"{candidate} appears potentially relevant for {position}. "
                "The provided resume text should be reviewed against the role requirements before submission."
            )
        return {
            "comments": {
                "recommendation_rationale": {
                    "strengths_summary": summary,
                    "risk_notes": "Pending consultant verification of achievements, motivation, compensation, and availability.",
                },
                "motivation": "Pending consultant input.",
                "role_fit": f"Initial fit for {position} requires consultant validation.",
            },
            "missing_information": [
                {"field": "consultant_notes", "message": "Add verified interview notes or call summary."}
            ],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_config_and_service.ConfigAndServiceTests.test_hiijob_agent_fallback_generates_deterministic_comments`

Expected: PASS.

## Task 3: Report Service

**Files:**
- Create: `core/report_service.py`
- Modify: `tests/test_config_and_service.py`

- [ ] **Step 1: Write failing service tests**

Append to `ConfigAndServiceTests`:

```python
    def test_report_service_creates_draft_and_card_url(self):
        from core.report_service import ReportService

        with tempfile.TemporaryDirectory() as tmp:
            service = ReportService(
                config_dir=PROJECT_ROOT / "config",
                data_dir=Path(tmp),
                public_base_url="http://testserver",
            )
            draft = service.create_draft({
                "brand_id": "default",
                "candidate_name": "Alice",
                "position_title": "Medical Director",
                "resume_text": "Oncology medical affairs leader.",
            })

            self.assertEqual(draft["status"], "draft")
            self.assertTrue(draft["report_id"].startswith("report_"))
            self.assertIn("/cards/reports/", draft["card_url"])

    def test_report_service_renders_docx(self):
        from core.report_service import ReportService

        with tempfile.TemporaryDirectory() as tmp:
            service = ReportService(
                config_dir=PROJECT_ROOT / "config",
                data_dir=Path(tmp),
                public_base_url="http://testserver",
            )
            draft = service.create_draft({
                "brand_id": "default",
                "candidate_name": "Alice",
                "position_title": "Medical Director",
            })
            service.generate_comments(draft["report_id"])
            rendered = service.render_report(draft["report_id"])

            self.assertEqual(rendered["status"], "confirmed")
            self.assertTrue((Path(tmp) / "outputs" / rendered["filename"]).exists())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_config_and_service.ConfigAndServiceTests.test_report_service_creates_draft_and_card_url tests.test_config_and_service.ConfigAndServiceTests.test_report_service_renders_docx`

Expected: ERROR because `core.report_service` is missing.

- [ ] **Step 3: Implement service**

Create `core/report_service.py` with:

```python
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Template

from .config_loader import get_loader
from .hiijob_agent import HiijobAgentClient
from .redactor import privacy_redact
from .renderer import ReportRenderer
from .validator import DataValidator


class ReportService:
    def __init__(
        self,
        config_dir: str | Path | None = None,
        data_dir: str | Path | None = None,
        public_base_url: str = "http://localhost:8767",
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
        record = {
            "report_id": report_id,
            "brand_id": brand_id,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
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
        record["updated_at"] = datetime.utcnow().isoformat() + "Z"
        brand_config = self.loader.load_brand(record["brand_id"])
        validation = DataValidator(brand_config).validate(record["data"])
        record["validation"] = validation.to_dict()
        self._save_record(record)
        return self._response_for(record)

    def render_report(self, report_id: str) -> dict[str, Any]:
        record = self._load_record(report_id)
        brand_config = self.loader.load_brand(record["brand_id"])
        template_config = None
        data = DataValidator(brand_config).prepare_draft_payload(record["data"])
        filename = self._filename(brand_config, data)
        output_path = self.outputs_dir / filename
        ReportRenderer(brand_config, template_config).render(data, output_path)
        validation = DataValidator(brand_config).validate(record["data"])
        record["status"] = "confirmed" if validation.is_valid else "draft"
        record["validation"] = validation.to_dict()
        record["output"] = {"filename": filename}
        record["updated_at"] = datetime.utcnow().isoformat() + "Z"
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_config_and_service`

Expected: PASS.

## Task 4: Review Card Template

**Files:**
- Create: `cards/report_review.html`
- Modify: `tests/test_config_and_service.py`

- [ ] **Step 1: Write failing card test**

Append to `ConfigAndServiceTests`:

```python
    def test_report_service_renders_review_card_html(self):
        from core.report_service import ReportService

        with tempfile.TemporaryDirectory() as tmp:
            service = ReportService(
                config_dir=PROJECT_ROOT / "config",
                data_dir=Path(tmp),
                public_base_url="http://testserver",
            )
            draft = service.create_draft({
                "brand_id": "default",
                "candidate_name": "Alice",
                "position_title": "Medical Director",
            })
            html = service.render_card_html(draft["report_id"])

            self.assertIn("Alice", html)
            self.assertIn("Medical Director", html)
            self.assertIn("Generate DOCX", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_config_and_service.ConfigAndServiceTests.test_report_service_renders_review_card_html`

Expected: ERROR because `cards/report_review.html` is missing.

- [ ] **Step 3: Implement card template**

Create `cards/report_review.html` with:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Report Review Card</title>
  <style>
    body { margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: #f6f8fa; color: #24292f; }
    main { max-width: 920px; margin: 0 auto; padding: 24px; }
    header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; border-bottom: 1px solid #d0d7de; padding-bottom: 16px; }
    h1 { font-size: 22px; margin: 0 0 6px; }
    h2 { font-size: 15px; margin: 20px 0 10px; }
    .status { border: 1px solid #d0d7de; border-radius: 8px; padding: 8px 12px; background: #fff; font-size: 13px; }
    .grid { display: grid; grid-template-columns: 260px 1fr; gap: 18px; margin-top: 18px; }
    .panel { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; }
    .label { color: #57606a; font-size: 12px; margin-top: 10px; }
    .value { font-weight: 600; margin-top: 3px; }
    textarea { width: 100%; min-height: 92px; box-sizing: border-box; border: 1px solid #d0d7de; border-radius: 6px; padding: 10px; font: inherit; }
    .missing { color: #9a6700; font-size: 13px; line-height: 1.5; }
    .actions { margin-top: 18px; display: flex; gap: 10px; }
    button, a.button { border: 1px solid #1f883d; background: #1f883d; color: #fff; border-radius: 6px; padding: 9px 12px; text-decoration: none; font-size: 14px; }
    @media (max-width: 760px) { .grid { grid-template-columns: 1fr; } header { flex-direction: column; } }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>{{ data.get("candidate_name", "Candidate") }}</h1>
      <div>{{ data.get("position_title", "Target Position") }}</div>
    </div>
    <div class="status">Status: {{ report.get("status", "draft") }}</div>
  </header>

  <section class="grid">
    <aside class="panel">
      <h2>Draft Fields</h2>
      <div class="label">Brand</div>
      <div class="value">{{ report.get("brand_id", "default") }}</div>
      <div class="label">Current Company</div>
      <div class="value">{{ data.get("current_company", "-") }}</div>
      <div class="label">Current Title</div>
      <div class="value">{{ data.get("current_title", "-") }}</div>
      <h2>Missing Information</h2>
      {% for item in validation.get("missing_items", []) %}
        <div class="missing">{{ item.get("field") }}: {{ item.get("message") }}</div>
      {% else %}
        <div class="missing">No required field gaps.</div>
      {% endfor %}
    </aside>
    <section class="panel">
      <h2>Recommendation Rationale</h2>
      {% set rationale = data.get("recommendation_rationale", {}) %}
      <div class="label">Strengths Summary</div>
      <textarea>{{ rationale.get("strengths_summary", "") }}</textarea>
      <div class="label">Risk Notes</div>
      <textarea>{{ rationale.get("risk_notes", "") }}</textarea>
      <div class="label">Motivation</div>
      <textarea>{{ data.get("motivation", "") }}</textarea>
      <div class="label">Role Fit</div>
      <textarea>{{ data.get("role_fit", "") }}</textarea>
      <div class="actions">
        <form method="post" action="{{ render_url }}">
          <button type="submit">Generate DOCX</button>
        </form>
      </div>
    </section>
  </section>
</main>
</body>
</html>
```

- [ ] **Step 4: Run card test to verify it passes**

Run: `python -m unittest tests.test_config_and_service.ConfigAndServiceTests.test_report_service_renders_review_card_html`

Expected: PASS.

## Task 5: FastAPI Bridge

**Files:**
- Create: `api/bridge.py`
- Create: `api/__init__.py`
- Modify: `tests/test_api_bridge.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api_bridge.py` with:

```python
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.bridge import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ApiBridgeTests(unittest.TestCase):
    def test_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(config_dir=PROJECT_ROOT / "config", data_dir=Path(tmp), public_base_url="http://testserver")
            client = TestClient(app)
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "ok")

    def test_draft_card_and_render_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(config_dir=PROJECT_ROOT / "config", data_dir=Path(tmp), public_base_url="http://testserver")
            client = TestClient(app)
            draft_response = client.post("/api/v1/reports/draft", json={
                "brand_id": "default",
                "candidate_name": "Alice",
                "position_title": "Medical Director",
            })
            self.assertEqual(draft_response.status_code, 200)
            report_id = draft_response.json()["report_id"]

            card_response = client.get(f"/cards/reports/{report_id}")
            self.assertEqual(card_response.status_code, 200)
            self.assertIn("Alice", card_response.text)

            comments_response = client.post(f"/api/v1/reports/{report_id}/comments", json={})
            self.assertEqual(comments_response.status_code, 200)

            render_response = client.post(f"/api/v1/reports/{report_id}/render")
            self.assertEqual(render_response.status_code, 200)
            self.assertTrue(render_response.json()["filename"].endswith(".docx"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_api_bridge`

Expected: ERROR because `api.bridge` is missing.

- [ ] **Step 3: Implement API bridge**

Create empty `api/__init__.py`.

Create `api/bridge.py` with:

```python
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from core.report_service import ReportService


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_id: str = "default"
    candidate_name: str = Field(min_length=1)
    position_title: str = Field(min_length=1)
    resume_text: str = ""
    resume_file_name: str = ""
    job_description: str = ""
    known_fields: dict[str, Any] = Field(default_factory=dict)
    source_context: dict[str, Any] = Field(default_factory=dict)


class CommentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: str = ""
    sections: list[str] = Field(default_factory=list)
    known_fields: dict[str, Any] = Field(default_factory=dict)


def create_app(
    config_dir: str | Path | None = None,
    data_dir: str | Path | None = None,
    public_base_url: str | None = None,
) -> FastAPI:
    app = FastAPI(title="Generic Report Tool", version="1.0.0")
    service = ReportService(
        config_dir=config_dir,
        data_dir=data_dir or os.environ.get("GENERIC_REPORT_DATA_DIR"),
        public_base_url=public_base_url or os.environ.get("GENERIC_REPORT_PUBLIC_BASE_URL", "http://localhost:8767"),
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "generic-report-tool", "version": "1.0.0"}

    @app.post("/api/v1/reports/draft")
    def create_draft(payload: DraftRequest) -> dict[str, Any]:
        data = payload.model_dump()
        data.update(data.pop("known_fields", {}))
        return service.create_draft(data)

    @app.post("/api/v1/reports/{report_id}/comments")
    def generate_comments(report_id: str, payload: CommentsRequest) -> dict[str, Any]:
        try:
            return service.generate_comments(report_id, feedback=payload.feedback)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.post("/api/v1/reports/{report_id}/render")
    def render_report(report_id: str) -> dict[str, Any]:
        try:
            return service.render_report(report_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.get("/cards/reports/{report_id}", response_class=HTMLResponse)
    def report_card(report_id: str) -> HTMLResponse:
        try:
            return HTMLResponse(service.render_card_html(report_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.get("/downloads/{filename}")
    def download(filename: str) -> FileResponse:
        try:
            return FileResponse(service.output_path(filename), filename=filename)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="File not found") from exc

    return app


app = create_app(config_dir=os.environ.get("GENERIC_REPORT_CONFIG_DIR"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    uvicorn.run(create_app(config_dir=os.environ.get("GENERIC_REPORT_CONFIG_DIR")), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_api_bridge`

Expected: PASS.

## Task 6: Streamlit Debug UI

**Files:**
- Create: `ui/streamlit_app.py`

- [ ] **Step 1: Create local debug UI**

Create `ui/streamlit_app.py` with:

```python
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.report_service import ReportService


def main() -> None:
    st.set_page_config(page_title="Generic Report Tool", layout="wide")
    st.title("Generic Report Tool")

    service = ReportService(
        config_dir=os.environ.get("GENERIC_REPORT_CONFIG_DIR", str(ROOT / "config")),
        data_dir=os.environ.get("GENERIC_REPORT_DATA_DIR", str(ROOT / "data")),
        public_base_url=os.environ.get("GENERIC_REPORT_PUBLIC_BASE_URL", "http://localhost:8767"),
    )

    brands = service.loader.list_brands()
    brand_ids = [item["brand_id"] for item in brands] or ["default"]
    brand_id = st.selectbox("Brand", brand_ids)
    candidate_name = st.text_input("Candidate Name")
    position_title = st.text_input("Position Title")
    current_company = st.text_input("Current Company")
    current_title = st.text_input("Current Title")
    job_description = st.text_area("Job Description", height=120)
    resume_text = st.text_area("Resume Text", height=220)

    if st.button("Create Draft", type="primary"):
        draft = service.create_draft({
            "brand_id": brand_id,
            "candidate_name": candidate_name,
            "position_title": position_title,
            "current_company": current_company,
            "current_title": current_title,
            "job_description": job_description,
            "resume_text": resume_text,
        })
        st.session_state["report_id"] = draft["report_id"]
        st.json(draft)

    report_id = st.session_state.get("report_id")
    if report_id:
        st.divider()
        st.subheader("Draft Actions")
        if st.button("Generate Comments"):
            st.json(service.generate_comments(report_id))
        if st.button("Render DOCX"):
            rendered = service.render_report(report_id)
            st.json(rendered)
            path = service.output_path(rendered["filename"])
            st.download_button("Download DOCX", path.read_bytes(), file_name=rendered["filename"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Compile UI**

Run: `python -m py_compile ui\streamlit_app.py`

Expected: exit code 0.

## Task 7: Final Verification

**Files:**
- Verify all created and modified files.

- [ ] **Step 1: Run full unit tests**

Run: `python -m unittest discover -s tests`

Expected: all tests pass.

- [ ] **Step 2: Run py_compile**

Run:

```powershell
python -m py_compile core\config_loader.py core\parser.py core\redactor.py core\prompt_engine.py core\validator.py core\renderer.py core\mcp_server.py core\hiijob_agent.py core\report_service.py api\bridge.py ui\streamlit_app.py
```

Expected: exit code 0.

- [ ] **Step 3: Run local health smoke test**

Start manually when needed:

```powershell
python api\bridge.py --host 127.0.0.1 --port 8767
```

Then open or request `http://127.0.0.1:8767/health`.

Expected:

```json
{"status":"ok","service":"generic-report-tool","version":"1.0.0"}
```

- [ ] **Step 4: Report deployment note**

If files are later migrated into `lobehub/services`, use:

```powershell
.\deploy-to-server.ps1
```

Expected: the script completes SCP, `docker cp`, restart, wait, and `verify-stack.sh`.
