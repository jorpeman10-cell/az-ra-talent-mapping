from __future__ import annotations

import argparse
import html
import os
import re
import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.report_service import ReportService
from core.parser import extract_uploaded_text

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8810
DEFAULT_PUBLIC_BASE_URL = f"http://localhost:{DEFAULT_PORT}"


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


def _infer_client_company(text: str) -> str:
    patterns = [
        r"(?:Client Company|Client|Company)\s*[:：]\s*([^\n\r,，;；]+)",
        r"(?:客户公司|客户|公司名称)\s*[:：]\s*([^\n\r,，;；]+)",
    ]
    for pattern in patterns:
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


def _brand_options(service: ReportService) -> str:
    options = []
    for item in service.loader.list_brands():
        brand_id = html.escape(item["brand_id"])
        label = html.escape(item.get("brand_name") or item["brand_id"])
        options.append(f'<option value="{brand_id}">{label}</option>')
    return "\n".join(options) or '<option value="default">Generic Referral Report</option>'


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
<html lang="zh-CN">
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
    input, select { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px 11px; font: inherit; background: #fff; }
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
    .link-button {
      display: inline-block;
      text-decoration: none;
      border: 1px solid #155eef;
      border-radius: 6px;
      padding: 8px 11px;
      background: #fff;
      color: #155eef;
      font: inherit;
      cursor: pointer;
    }
    .link-button:hover {
      background: #155eef;
      color: #fff;
    }
    .link-button:disabled {
      opacity: .5;
      cursor: wait;
    }
    @media (max-width: 720px) { main { padding: 18px; } header, form { display: block; } label { margin-top: 14px; } .actions { margin-top: 16px; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Generic Report Tool</h1>
        <p>上传简历和 JD，生成候选人报告卡片</p>
      </div>
      <div>
        <p>Agent: __AGENT_STATUS__</p>
        <a href="health">Health check</a>
      </div>
    </header>

    <form id="draft-form" enctype="multipart/form-data">
      <label>
        客户品牌
        <select name="brand_id">
          __BRAND_OPTIONS__
        </select>
      </label>
      <label>
        候选人姓名
        <input name="candidate_name" autocomplete="name" placeholder="例如：张三" required>
      </label>
      <label>
        目标岗位
        <input name="position_title" placeholder="例如：Medical Director" required>
      </label>
      <label>
        当前公司
        <input name="current_company" placeholder="可选">
      </label>
      <label>
        当前职位
        <input name="current_title" placeholder="可选">
      </label>
      <label class="full">
        客户公司
        <input name="client_company" placeholder="可手填；留空时会尝试从 JD 中识别">
      </label>
      <label class="full">
        简历文件
        <input type="file" name="resume_file" accept=".pdf,.docx,.txt,.md" required>
        <span class="hint">必填。当前支持 PDF / DOCX / TXT / MD。</span>
      </label>
      <label class="full">
        JD 文件
        <input type="file" name="jd_file" accept=".pdf,.docx,.txt,.md">
        <span class="hint">建议上传。可包含职位描述、客户要求、推荐关注点。</span>
      </label>
      <div class="actions">
        <button type="submit">生成报告卡片</button>
        <span class="status" id="status"></span>
      </div>
    </form>

    <section class="result" id="result">
      <strong>报告草稿已生成</strong>
      <div class="links">
        <a class="link-button" id="card-link" target="_blank" rel="noreferrer">打开审核卡片</a>
        <button class="link-button" id="render-btn" type="button">生成 DOCX</button>
      </div>
    </section>
  </main>
  <script>
    const form = document.getElementById('draft-form');
    const statusEl = document.getElementById('status');
    const resultEl = document.getElementById('result');
    const cardLink = document.getElementById('card-link');
    const renderBtn = document.getElementById('render-btn');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = form.querySelector('button');
      const data = new FormData(form);
      button.disabled = true;
      statusEl.textContent = '正在生成...';
      resultEl.style.display = 'none';
      try {
        const response = await fetch('api/v1/reports/draft-from-files', {
          method: 'POST',
          body: data
        });
        if (!response.ok) throw new Error(await response.text());
        const payload = await response.json();
        cardLink.href = payload.card_url;
        renderBtn.dataset.url = payload.render_url;
        statusEl.textContent = payload.validation && payload.validation.is_valid ? '草稿完整' : '草稿已生成，可在卡片中补充信息';
        resultEl.style.display = 'block';
      } catch (error) {
        statusEl.textContent = '生成失败：' + error.message;
      } finally {
        button.disabled = false;
      }
    });

    renderBtn.addEventListener('click', async () => {
      const url = renderBtn.dataset.url;
      if (!url) return;
      renderBtn.disabled = true;
      statusEl.textContent = '正在生成 DOCX...';
      try {
        const response = await fetch(url, { method: 'POST' });
        if (!response.ok) throw new Error(await response.text());
        const result = await response.json();
        if (result.download_url) {
          window.open(result.download_url, '_blank');
          statusEl.textContent = 'DOCX 已生成';
        } else {
          statusEl.textContent = '生成完成';
        }
      } catch (error) {
        statusEl.textContent = 'DOCX 生成失败：' + error.message;
      } finally {
        renderBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""
        page = page.replace("__BRAND_OPTIONS__", _brand_options(service))
        page = page.replace("__AGENT_STATUS__", html.escape(agent_status))
        return HTMLResponse(page)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.post("/api/v1/reports/draft")
    def create_draft(payload: DraftRequest) -> dict[str, Any]:
        data = payload.model_dump()
        data.update(data.pop("known_fields", {}))
        return service.create_draft(data)

    @app.post("/api/v1/reports/draft-from-files")
    async def create_draft_from_files(
        brand_id: str = Form("default"),
        candidate_name: str = Form(...),
        position_title: str = Form(...),
        current_company: str = Form(""),
        current_title: str = Form(""),
        client_company: str = Form(""),
        resume_file: UploadFile = File(...),
        jd_file: UploadFile | None = File(None),
    ) -> dict[str, Any]:
        resume_name, resume_text = await _extract_upload(resume_file)
        jd_name, jd_text = await _extract_upload(jd_file)
        inferred_client_company = client_company.strip() or _infer_client_company(jd_text)
        payload = {
            "brand_id": brand_id,
            "candidate_name": candidate_name,
            "position_title": position_title,
            "resume_file_name": resume_name,
            "resume_text": resume_text,
            "job_description": jd_text,
            "jd_file_name": jd_name,
            "current_company": current_company.strip(),
            "current_title": current_title.strip(),
            "client_company": inferred_client_company,
            "source_files": {
                "resume_file_name": resume_name,
                "jd_file_name": jd_name,
            },
        }
        response = service.create_draft(payload)
        response["source_files"] = payload["source_files"]
        response["known_fields"] = {
            "current_company": payload["current_company"],
            "current_title": payload["current_title"],
            "client_company": payload["client_company"],
        }
        return response

    @app.post("/api/v1/reports/{report_id}/comments")
    def generate_comments(report_id: str, payload: CommentsRequest) -> dict[str, Any]:
        try:
            result = service.generate_comments(report_id, feedback=payload.feedback)
            # 返回完整的数据结构，包含 report_id 和 data 字段
            return {
                "report_id": report_id,
                "data": result.get("data", {}),
                "validation": result.get("validation", {}),
                "status": result.get("status", "draft"),
                "missing_information": result.get("missing_information", []),
            }
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
