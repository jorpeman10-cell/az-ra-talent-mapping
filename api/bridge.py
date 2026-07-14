from __future__ import annotations

import argparse
import base64
import html
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.candidate_brief import ResumeQualityError
from core.report_service import ReportService
from core.parser import extract_uploaded_text

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8810
DEFAULT_PUBLIC_BASE_URL = f"http://localhost:{DEFAULT_PORT}"


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_id: str = "tstar"
    candidate_name: str = ""
    position_title: str = ""
    resume_text: str = ""
    resume_source_id: str = ""
    candidate_brief_id: str = ""
    resume_file_name: str = ""
    job_description: str = ""
    salary_info: str = ""
    report_style: str = "tstar_warm"
    professional_photo_data_uri: str = ""
    professional_photo_file_name: str = ""
    professional_photo_required: bool = False
    known_fields: dict[str, Any] = Field(default_factory=dict)
    source_context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_identity_or_resume_reference(self) -> "DraftRequest":
        has_reference = bool(self.candidate_brief_id or self.resume_source_id or self.resume_text)
        if not has_reference and (not self.candidate_name or not self.position_title):
            raise ValueError("candidate_name and position_title are required unless a resume reference is provided")
        return self


class ResumeSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    file_name: str = ""
    source_type: str = "upload"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_source_id: str = Field(min_length=1)
    known_fields: dict[str, Any] = Field(default_factory=dict)


class CommentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: str = ""
    sections: list[str] = Field(default_factory=list)
    known_fields: dict[str, Any] = Field(default_factory=dict)


class UpdateReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    known_fields: dict[str, Any] = Field(default_factory=dict)
    feedback: str = ""


def _infer_client_company(text: str) -> str:
    colon = ":" + "\uFF1A"
    separators = "\n\r,\uFF0C;\uFF1B"
    labels = ["Client Company", "Client", "Company", "\u5BA2\u6237\u516C\u53F8", "\u5BA2\u6237", "\u516C\u53F8\u540D\u79F0"]
    for label in labels:
        pattern = rf"(?:{re.escape(label)})\s*[{colon}]\s*([^{separators}]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""

async def _extract_upload(upload: UploadFile | None) -> tuple[str, str]:
    if upload is None or not upload.filename:
        return "", ""
    content = await upload.read()
    if not content:
        return upload.filename, ""
    try:
        return upload.filename, extract_uploaded_text(upload.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _extract_photo_upload(upload: UploadFile | None) -> tuple[str, str]:
    if upload is None or not upload.filename:
        return "", ""
    content = await upload.read()
    if not content:
        return upload.filename, ""
    suffix = Path(upload.filename).suffix.lower()
    mime_by_suffix = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    mime_type = mime_by_suffix.get(suffix)
    if not mime_type:
        raise HTTPException(status_code=422, detail="Professional photo must be JPG, PNG, or WEBP.")
    encoded = base64.b64encode(content).decode("ascii")
    return upload.filename, f"data:{mime_type};base64,{encoded}"


def _brand_options(service: ReportService, selected_brand_id: str = "tstar") -> str:
    options = []
    brands = sorted(
        [
            item
            for item in service.loader.list_brands()
            if item.get("brand_id") != "default"
        ],
        key=lambda item: (0 if item["brand_id"] == selected_brand_id else 1, item["brand_id"]),
    )
    for item in brands:
        raw_brand_id = item["brand_id"]
        brand_id = html.escape(raw_brand_id)
        label = html.escape(item.get("brand_name") or item["brand_id"])
        selected = " selected" if raw_brand_id == selected_brand_id else ""
        options.append(f'<option value="{brand_id}"{selected}>{label}</option>')
    return "\n".join(options) or '<option value="tstar">T-STAR Candidate Referral Report</option>'


def create_app(
    config_dir: str | Path | None = None,
    data_dir: str | Path | None = None,
    public_base_url: str | None = None,
) -> FastAPI:
    app = FastAPI(title="Generic Report Tool", version="1.0.0")
    service = ReportService(
        config_dir=config_dir,
        data_dir=data_dir or os.environ.get("GENERIC_REPORT_DATA_DIR"),
        public_base_url=public_base_url
        or os.environ.get("GENERIC_REPORT_PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL),
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "generic-report-tool", "version": "1.0.0"}

    @app.get("/", response_class=HTMLResponse)
    def home() -> HTMLResponse:
        agent_status = "connected" if os.environ.get("HIIJOB_AGENT_BASE_URL") else "fallback"
        page = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Generic Report Tool</title>
  <style>
    :root { color-scheme: light; }
    body { margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; color: #172033; background: #f5f7fb; }
    main { max-width: 1080px; margin: 0 auto; padding: 28px; }
    header { display: flex; justify-content: space-between; gap: 16px; align-items: center; margin-bottom: 20px; }
    h1 { font-size: 28px; margin: 0 0 6px; }
    p { margin: 0; color: #5f6b7a; }
    form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; background: #fff; border: 1px solid #d9e0ea; border-radius: 8px; padding: 18px; }
    label { display: grid; gap: 7px; font-size: 13px; font-weight: 600; color: #344054; }
    input, select, textarea { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px 11px; font: inherit; background: #fff; }
    textarea { min-height: 104px; resize: vertical; }
    input[type="file"] { padding: 9px; }
    .full { grid-column: 1 / -1; }
    .hint { font-weight: 400; color: #667085; font-size: 12px; }
    .actions { grid-column: 1 / -1; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    button { border: 0; background: #155eef; color: #fff; border-radius: 6px; padding: 10px 15px; font: inherit; font-weight: 700; cursor: pointer; }
    button:disabled { opacity: .62; cursor: wait; }
    a { color: #155eef; }
    .status { min-height: 22px; color: #475467; }
    .result { margin-top: 16px; background: #fff; border: 1px solid #d9e0ea; border-radius: 8px; padding: 16px; display: none; }
    .result strong { display: block; margin-bottom: 8px; }
    .links { display: flex; gap: 12px; flex-wrap: wrap; }
    .link-button { display: inline-block; text-decoration: none; border: 1px solid #155eef; border-radius: 6px; padding: 8px 11px; background: #fff; color: #155eef; font: inherit; cursor: pointer; }
    .link-button:hover { background: #155eef; color: #fff; }
    .link-button:disabled { opacity: .5; cursor: wait; }
    @media (max-width: 720px) { main { padding: 18px; } header, form { display: block; } label { margin-top: 14px; } .actions { margin-top: 16px; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Generic Report Tool</h1>
        <p>Upload a resume and optional JD to create a candidate report card.</p>
      </div>
      <div>
        <p>Agent: __AGENT_STATUS__</p>
        <a href="health">Health check</a>
      </div>
    </header>

    <form id="draft-form" enctype="multipart/form-data">
      <label>
        Brand
        <select name="brand_id">
          __BRAND_OPTIONS__
        </select>
      </label>
      <label>
        Report Style
        <select name="report_style">
          <option value="tstar_warm">T-STAR 紫红商务 / 双语模板</option>
          <option value="consulting_blue">Consulting Blue / McKinsey-like</option>
        </select>
      </label>
      <label>
        Candidate Name
        <input name="candidate_name" autocomplete="name" placeholder="Example: Zhang San" required>
      </label>
      <label>
        Target Role
        <input name="position_title" placeholder="Example: Medical Director" required>
      </label>
      <label>
        Current Company
        <input name="current_company" placeholder="Optional">
      </label>
      <label>
        Current Title
        <input name="current_title" placeholder="Optional">
      </label>
      <label class="full">
        Salary Information / 薪资信息
        <input name="salary_info" placeholder="Optional / 可选：current package, expected salary, bonus, notice period">
      </label>
      <label class="full">
        Client Company
        <input name="client_company" placeholder="Optional; leave blank to infer from JD">
      </label>
      <label class="full">
        Resume File
        <input type="file" name="resume_file" accept=".pdf,.docx,.txt,.md" required>
        <span class="hint">Required. Supports PDF / DOCX / TXT / MD.</span>
      </label>
      <label class="full">
        Professional Photo / 职业照
        <input type="file" name="professional_photo" accept=".jpg,.jpeg,.png,.webp">
        <span class="hint">Optional. If provided, the report will fit it into the fixed photo area automatically.</span>
        <span class="hint"><input type="checkbox" name="professional_photo_required" value="true" style="width:auto; margin-right:6px;">Keep a light photo placeholder when no photo is uploaded.</span>
      </label>
      <label class="full">
        JD File
        <input type="file" name="jd_file" accept=".pdf,.docx,.txt,.md">
        <span class="hint">Optional. Can include role description, client requirements, and referral notes.</span>
      </label>
      <label class="full">
        JD Text
        <textarea name="jd_text" placeholder="Optional: paste role responsibilities, client requirements, and referral notes when there is no formal JD file."></textarea>
        <span class="hint">JD file text and JD text are merged for client inference, AI comments, and report generation.</span>
      </label>
      <div class="actions">
        <button type="submit">Create Report Card</button>
        <span class="status" id="status"></span>
      </div>
    </form>

    <section class="result" id="result">
      <strong>Draft created</strong>
      <div class="links">
        <a class="link-button" id="card-link" target="_blank" rel="noreferrer">Open Review Card</a>
        <button class="link-button" id="render-btn" type="button">Generate DOCX</button>
        <button class="link-button" id="render-html-btn" type="button">Generate HTML</button>
      </div>
    </section>
  </main>
  <script>
    const form = document.getElementById('draft-form');
    const statusEl = document.getElementById('status');
    const resultEl = document.getElementById('result');
    const cardLink = document.getElementById('card-link');
    const renderBtn = document.getElementById('render-btn');
    const renderHtmlBtn = document.getElementById('render-html-btn');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = form.querySelector('button');
      const data = new FormData(form);
      button.disabled = true;
      statusEl.textContent = 'Creating...';
      resultEl.style.display = 'none';
      try {
        const response = await fetch('api/v1/reports/draft-from-files', { method: 'POST', body: data });
        if (!response.ok) throw new Error(await readErrorMessage(response));
        const payload = await response.json();
        cardLink.href = payload.card_url;
        renderBtn.dataset.url = payload.render_url;
        const renderBaseUrl = payload.render_url.endsWith('/render') ? payload.render_url.slice(0, -7) : payload.render_url;
        renderHtmlBtn.dataset.url = `${renderBaseUrl}/render-html`;
        statusEl.textContent = payload.validation && payload.validation.is_valid ? 'Draft complete' : 'Draft created; complete missing fields in the review card.';
        resultEl.style.display = 'block';
      } catch (error) {
        statusEl.textContent = 'Create failed: ' + error.message;
      } finally {
        button.disabled = false;
      }
    });

    async function readErrorMessage(response) {
      const text = await response.text();
      return formatCreateErrorMessage(response, text);
    }

    function formatCreateErrorMessage(response, text) {
      if (response.status === 413) {
        return 'Upload is too large / 上传内容过大。Please use a smaller resume or JD file, or ask an admin to increase the server upload limit.';
      }
      try {
        const payload = JSON.parse(text);
        if (payload.detail) return Array.isArray(payload.detail) ? JSON.stringify(payload.detail) : String(payload.detail);
      } catch (_) {}
      const plainText = text.replace(/<[^>]*>/g, ' ').replace(/\\s+/g, ' ').trim();
      return plainText || `Request failed (${response.status})`;
    }

    async function renderOutput(button, label) {
      const url = button.dataset.url;
      if (!url) return;
      button.disabled = true;
      statusEl.textContent = `Generating ${label}...`;
      try {
        const response = await fetch(url, { method: 'POST' });
        if (!response.ok) throw new Error(await response.text());
        const result = await response.json();
        if (result.filename && result.report_id) {
          const format = label.toLowerCase();
          const previewUrl = `cards/reports/${result.report_id}/preview?format=${format}&filename=${encodeURIComponent(result.filename)}`;
          window.open(previewUrl, '_blank');
          statusEl.textContent = `${label} generated`;
        } else if (result.download_url) {
          window.open(result.download_url, '_blank');
          statusEl.textContent = `${label} generated`;
        } else {
          statusEl.textContent = 'Generated';
        }
      } catch (error) {
        statusEl.textContent = `${label} generation failed: ` + error.message;
      } finally {
        button.disabled = false;
      }
    }

    renderBtn.addEventListener('click', () => renderOutput(renderBtn, 'DOCX'));
    renderHtmlBtn.addEventListener('click', () => renderOutput(renderHtmlBtn, 'HTML'));
  </script>
</body>
</html>
"""
        page = page.replace("__BRAND_OPTIONS__", _brand_options(service, "tstar"))
        page = page.replace("__AGENT_STATUS__", html.escape(agent_status))
        return HTMLResponse(page)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.post("/api/v1/reports/draft")
    def create_draft(payload: DraftRequest) -> dict[str, Any]:
        data = payload.model_dump()
        data.update(data.pop("known_fields", {}))
        try:
            return service.create_draft(data)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/resume-sources")
    def create_resume_source(payload: ResumeSourceRequest) -> dict[str, Any]:
        metadata = dict(payload.metadata or {})
        if payload.file_name:
            metadata["file_name"] = payload.file_name
        metadata["source_type"] = payload.source_type
        try:
            source = service.create_resume_source(payload.text, metadata=metadata)
            return {
                "resume_source_id": source["resume_source_id"],
                "content_hash": source["content_hash"],
                "char_count": source["char_count"],
                "metadata": source.get("metadata", {}),
            }
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/candidate-briefs")
    def create_candidate_brief(payload: CandidateBriefRequest) -> dict[str, Any]:
        try:
            brief = service.create_candidate_brief(payload.resume_source_id, payload.known_fields)
            return {
                "candidate_brief_id": brief["candidate_brief_id"],
                "resume_source_id": brief["resume_source_id"],
                "candidate_brief": brief,
            }
        except ResumeQualityError as exc:
            raise HTTPException(status_code=422, detail=exc.to_detail()) from exc
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/candidate-briefs/{candidate_brief_id}")
    def get_candidate_brief(candidate_brief_id: str) -> dict[str, Any]:
        try:
            brief = service.get_candidate_brief(candidate_brief_id)
            return {
                "candidate_brief_id": brief["candidate_brief_id"],
                "resume_source_id": brief["resume_source_id"],
                "candidate_brief": brief,
            }
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/reports/draft-from-files")
    async def create_draft_from_files(
        brand_id: str = Form("tstar"),
        candidate_name: str = Form(...),
        position_title: str = Form(...),
        current_company: str = Form(""),
        current_title: str = Form(""),
        salary_info: str = Form(""),
        client_company: str = Form(""),
        jd_text: str = Form(""),
        report_style: str = Form("tstar_warm"),
        professional_photo_required: str = Form(""),
        resume_file: UploadFile = File(...),
        professional_photo: UploadFile | None = File(None),
        jd_file: UploadFile | None = File(None),
    ) -> dict[str, Any]:
        resume_name, resume_text = await _extract_upload(resume_file)
        photo_name, photo_data_uri = await _extract_photo_upload(professional_photo)
        jd_name, jd_file_text = await _extract_upload(jd_file)
        jd_description = "\n\n".join(part.strip() for part in [jd_file_text, jd_text] if part.strip())
        inferred_client_company = client_company.strip() or _infer_client_company(jd_description)
        payload = {
            "brand_id": brand_id,
            "candidate_name": candidate_name,
            "position_title": position_title,
            "resume_file_name": resume_name,
            "resume_text": resume_text,
            "job_description": jd_description,
            "report_style": report_style,
            "jd_file_name": jd_name,
            "current_company": current_company.strip(),
            "current_title": current_title.strip(),
            "salary_info": salary_info.strip(),
            "client_company": inferred_client_company,
            "professional_photo_file_name": photo_name,
            "professional_photo_data_uri": photo_data_uri,
            "professional_photo_required": professional_photo_required.strip().lower()
            in {"1", "true", "yes", "on"},
            "source_files": {
                "resume_file_name": resume_name,
                "jd_file_name": jd_name,
                "professional_photo_file_name": photo_name,
            },
        }
        response = service.create_draft(payload)
        response["source_files"] = payload["source_files"]
        response["known_fields"] = {
            "current_company": payload["current_company"],
            "current_title": payload["current_title"],
            "salary_info": payload["salary_info"],
            "client_company": payload["client_company"],
        }
        return response

    @app.post("/api/v1/reports/{report_id}/comments")
    def generate_comments(report_id: str, payload: CommentsRequest) -> dict[str, Any]:
        try:
            if payload.known_fields:
                service.update_report(report_id, payload.known_fields)
            result = service.generate_comments(report_id, feedback=payload.feedback)
            # 杩斿洖瀹屾暣鐨勬暟鎹粨鏋勶紝鍖呭惈 report_id 鍜?data 瀛楁
            return {
                "report_id": report_id,
                "data": result.get("data", {}),
                "validation": result.get("validation", {}),
                "status": result.get("status", "draft"),
                "missing_information": result.get("missing_information", []),
            }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.post("/api/v1/reports/{report_id}/update")
    def update_report(report_id: str, payload: UpdateReportRequest) -> dict[str, Any]:
        try:
            return service.update_report(
                report_id,
                known_fields=payload.known_fields,
                feedback=payload.feedback,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.post("/api/v1/reports/{report_id}/render")
    def render_report(report_id: str) -> dict[str, Any]:
        try:
            return service.render_report(report_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.post("/api/v1/reports/{report_id}/render-html")
    def render_html_report(report_id: str) -> dict[str, Any]:
        try:
            return service.render_html_report(report_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.post("/api/v1/reports/{report_id}/render-pdf")
    def render_pdf_report(report_id: str) -> dict[str, Any]:
        try:
            return service.render_pdf_report(report_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.get("/cards/reports/{report_id}", response_class=HTMLResponse)
    def report_card(report_id: str) -> HTMLResponse:
        try:
            return HTMLResponse(service.render_card_html(report_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.post("/cards/reports/{report_id}/render")
    def report_card_render(report_id: str) -> RedirectResponse:
        try:
            rendered = service.render_report(report_id)
            filename = quote(rendered["filename"])
            return RedirectResponse(
                url=f"{service.public_base_url}/cards/reports/{report_id}/preview?format=docx&filename={filename}",
                status_code=303,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.post("/cards/reports/{report_id}/render-html")
    def report_card_render_html(report_id: str) -> RedirectResponse:
        try:
            rendered = service.render_html_report(report_id)
            filename = quote(rendered["filename"])
            return RedirectResponse(
                url=f"{service.public_base_url}/cards/reports/{report_id}/preview?format=html&filename={filename}",
                status_code=303,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.post("/cards/reports/{report_id}/render-pdf")
    def report_card_render_pdf(report_id: str) -> RedirectResponse:
        try:
            rendered = service.render_pdf_report(report_id)
            filename = quote(rendered["filename"])
            return RedirectResponse(
                url=f"{service.public_base_url}/cards/reports/{report_id}/preview?format=pdf&filename={filename}",
                status_code=303,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.get("/cards/reports/{report_id}/preview", response_class=HTMLResponse)
    def report_preview(report_id: str, format: str = "docx", filename: str = "") -> HTMLResponse:
        try:
            service.output_path(filename)
            context = service.card_context(report_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Report output not found") from exc

        safe_format = html.escape(format.lower())
        safe_filename = html.escape(Path(filename).name)
        quoted_filename = quote(Path(filename).name)
        download_url = f"{service.public_base_url}/downloads/{quoted_filename}"
        preview_url = f"{service.public_base_url}/preview-files/{quoted_filename}"
        safe_download_url = html.escape(download_url, quote=True)
        safe_preview_url = html.escape(preview_url, quote=True)
        candidate = html.escape(str(context.get("data", {}).get("candidate_name") or "Candidate"))
        position = html.escape(str(context.get("data", {}).get("position_title") or "Target Role"))
        card_url = html.escape(f"{service.public_base_url}/cards/reports/{report_id}", quote=True)
        download_label = f"Download {safe_format.upper()}"
        if safe_format == "html":
            print_button = '<button class="button secondary" type="button" onclick="window.frames[0].focus(); window.frames[0].print();">Print / Save PDF</button>'
            preview_body = f'<iframe class="preview-frame" src="{safe_preview_url}" title="Report preview / 报告预览"></iframe>'
        elif safe_format == "pdf":
            print_button = ""
            preview_body = f'<iframe class="preview-frame" src="{safe_preview_url}" title="Report preview / 报告预览"></iframe>'
        else:
            print_button = ""
            preview_body = (
                '<div class="docx-note">'
                "<h2>DOCX is ready / DOCX 已生成</h2>"
                "<p>Browser preview is not reliable for Word files. Confirm the file name and download it for final review. / Word 文件不适合在浏览器内预览，请确认文件名后下载审阅。</p>"
                "</div>"
            )
        page = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Report Preview / 报告预览</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: #f6f8fa; color: #172033; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ font-size: 24px; margin: 0 0 6px; }}
    p {{ margin: 0; color: #57606a; }}
    .panel {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; }}
    .meta {{ display: grid; grid-template-columns: 140px 1fr; gap: 8px 14px; margin-top: 14px; font-size: 14px; }}
    .label {{ color: #57606a; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 16px; }}
    .button {{ display: inline-block; border: 1px solid #155eef; background: #155eef; color: #fff; border-radius: 6px; padding: 9px 12px; text-decoration: none; font-weight: 700; }}
    .button.secondary {{ background: #fff; color: #155eef; }}
    .preview-frame {{ width: 100%; height: 78vh; border: 1px solid #d0d7de; border-radius: 8px; background: #fff; margin-top: 16px; }}
    .docx-note {{ margin-top: 16px; border: 1px dashed #8c959f; border-radius: 8px; padding: 22px; background: #fff; }}
    .docx-note h2 {{ margin: 0 0 8px; font-size: 18px; }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Report Preview / 报告预览</h1>
      <p>{candidate} / {position}</p>
    </div>
  </header>
  <section class="panel">
    <div class="meta">
      <div class="label">Format / 格式</div><div>{safe_format.upper()}</div>
      <div class="label">File / 文件</div><div>{safe_filename}</div>
      <div class="label">Status / 状态</div><div>Generated / 已生成</div>
    </div>
    <div class="actions">
      <a class="button" href="{safe_download_url}">{download_label}</a>
      {print_button}
      <a class="button secondary" href="{card_url}">Back to Review Card / 返回审核卡片</a>
    </div>
  </section>
  {preview_body}
</main>
</body>
</html>
"""
        return HTMLResponse(page)

    @app.get("/preview-files/{filename}")
    def preview_file(filename: str) -> FileResponse:
        try:
            path = service.output_path(filename)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="File not found") from exc
        extension = path.suffix.lower()
        media_type = {
            ".html": "text/html; charset=utf-8",
            ".pdf": "application/pdf",
        }.get(extension, "application/octet-stream")
        return FileResponse(
            path,
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{path.name}"',
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    @app.get("/downloads/{filename}")
    def download(filename: str) -> FileResponse:
        try:
            return FileResponse(
                service.output_path(filename),
                filename=filename,
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                },
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="File not found") from exc

    return app


app = create_app(config_dir=os.environ.get("GENERIC_REPORT_CONFIG_DIR"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    public_base_url = os.environ.get("GENERIC_REPORT_PUBLIC_BASE_URL")
    if not public_base_url:
        public_host = "localhost" if args.host == "0.0.0.0" else args.host
        public_base_url = f"http://{public_host}:{args.port}"
    uvicorn.run(
        create_app(
            config_dir=os.environ.get("GENERIC_REPORT_CONFIG_DIR"),
            public_base_url=public_base_url,
        ),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
