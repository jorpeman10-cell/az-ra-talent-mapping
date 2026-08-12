# Resume Source Appendix Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit T-STAR report modes for a structured-only resume or a structured resume followed by a faithful source-file appendix, without changing the AZ client-template flow.

**Architecture:** Store uploaded source bytes in a content-addressed file store and keep only the source ID in report JSON. The existing parser continues to build structured report data from the same upload. The DOCX renderer always produces the structured template and conditionally delegates source appendix rendering by file type.

**Tech Stack:** FastAPI, python-docx, PyMuPDF, LibreOffice headless conversion, unittest.

## Global Constraints

- `structured_only` never contains source pages or raw-source text.
- `structured_with_source_appendix` always contains the structured report plus the complete source appendix.
- PDF and DOCX preserve source pages visually; TXT/MD preserve complete source order and line breaks.
- Missing or failed source conversion must fail explicitly; no silent fallback.
- AZ remains isolated and is not modified by these T-STAR modes.
- Preserve the current Kimi-updated T-STAR template body.

---

### Task 1: Content-addressed source file store

**Files:**
- Create: `core/source_file_store.py`
- Test: `tests/test_source_file_store.py`

**Interfaces:**
- Produces: `SourceFileStore.create(filename: str, content: bytes, mime_type: str = "") -> dict`
- Produces: `SourceFileStore.load(source_file_id: str) -> dict`
- Produces: `SourceFileStore.path_for(source_file_id: str) -> Path`

- [ ] Write tests for byte preservation, hash deduplication, metadata, invalid IDs, and allowed extensions.
- [ ] Run tests and confirm they fail because the store does not exist.
- [ ] Implement the store under `data/source_files` with `rf_<sha256-prefix>` IDs and sidecar JSON metadata.
- [ ] Run the focused tests and commit.

### Task 2: Upload and report data contract

**Files:**
- Modify: `api/bridge.py`
- Modify: `core/report_service.py`
- Test: `tests/test_api_bridge.py`
- Test: `tests/test_config_and_service.py`

**Interfaces:**
- Consumes: `SourceFileStore`
- Produces report fields: `resume_appendix_mode`, `resume_source_file_id`, `resume_source_file_name`, `resume_source_mime_type`, `resume_source_content_hash`

- [ ] Write failing API tests for default `structured_only`, selected appendix mode, original byte persistence, and appendix mode without a source reference.
- [ ] Add the two-mode UI control and server-side enum validation.
- [ ] Save upload bytes before text extraction and ensure source metadata and parsed text share the same source hash.
- [ ] Add JSON/API base64 support for direct tool calls while keeping raw bytes out of draft JSON.
- [ ] Run focused API/service tests and commit.

### Task 3: Source appendix renderer

**Files:**
- Create: `core/source_appendix.py`
- Modify: `core/renderer.py`
- Modify: `core/report_service.py`
- Modify: `requirements-api.txt`
- Modify: `requirements.txt`
- Modify: `Dockerfile`
- Test: `tests/test_source_appendix.py`
- Test: `tests/test_config_and_service.py`

**Interfaces:**
- Produces: `append_source_file(doc: Document, source_path: Path, source_name: str) -> SourceAppendixResult`
- PDF: PyMuPDF page rendering at 150 DPI.
- DOCX: LibreOffice headless conversion to PDF, then the PDF path.
- TXT/MD: complete UTF-8 text with original ordering and blank lines.

- [ ] Write failing tests for PDF page count/order, TXT complete text, missing source, and structured-only omission.
- [ ] Implement renderer with explicit `source_appendix_render_failed` and size/page limits.
- [ ] Remove the legacy raw parsed-text appendix from T-STAR structured-only output.
- [ ] Append the source only for `structured_with_source_appendix`.
- [ ] Run focused renderer/service tests and commit.

### Task 4: End-to-end regression and visual QA

**Files:**
- Modify: `tests/test_api_bridge.py`
- Modify: `tests/test_config_and_service.py`

**Interfaces:**
- Verifies public behavior only.

- [ ] Add E2E tests for DOCX structured-only and structured-plus-PDF outputs.
- [ ] Verify AZ-facing code and templates are untouched.
- [ ] Run the full unittest suite.
- [ ] Render representative DOCX outputs to PDF/PNG and inspect page count, clipping, page order, and absence of duplicate raw text.
- [ ] Run `git diff --check` and commit the final regression coverage.
