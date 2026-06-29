# Generic Report Tool B9 Hiijob Card Integration Design

Date: 2026-06-29
Status: Draft for user review

## Context

`generic-report-tool` is the reusable report-generation product. Hiijob/LobeHub should provide the user entry point, Agent routing, and review card surface, but the report engine must remain independent and reusable for non-Hiijob customers.

The current project has core modules for configuration loading, resume parsing, privacy redaction, validation, DOCX rendering, prompt rendering, and a lightweight MCP/HTTP server. The `config/`, `ui/`, `api/`, and `tests/` directories are currently empty. `DEVELOPMENT_GUIDE.md` lists Streamlit UI, LLM integration, API completion, and tests as the MVP items.

Hiijob project guidance in `lobehub/CLAUDE.md` classifies independent product services as Group B work. Group B services must be isolated from `federation_gateway`, define contracts before implementation, expose `GET /health`, use env vars for credentials/configuration, include tests, and integrate through Compose/CI. Codex must not directly edit A-class MCP/Agent/DB ownership such as `federation_gateway/mcp_server.py` or LobeHub Agent records.

## Decision

Build the generic report capability as a B-class product service, tentatively `B9 generic-report-tool`. Hiijob will be a thin caller:

- The generic service owns report configuration, draft state, AI comment generation adapter, card HTML, and DOCX rendering.
- Hiijob Report Agent or MCP tools call the service and display the returned `card_url`.
- Hiijob card integration does not move report business logic into `federation_gateway`.
- Streamlit may remain a local/debug UI, but the primary user flow is a Hiijob-style review card.

## Architecture

### Service Boundary

The service will live first in `generic-report-tool`. When integrated into the Hiijob deployment, it can be copied or migrated into `lobehub/services/generic_report_tool` and registered as B9.

The service must not import or call `federation_gateway`, Gllue, Hunter, or LobeHub database code. Callers pass candidate, position, resume, and known-field context into the service.

### Runtime Components

- `core/report_service.py`
  Orchestrates draft creation, validation, AI comment generation, and rendering.

- `core/hiijob_agent.py`
  Wraps the Hiijob Agent call as a replaceable adapter. It reads `HIIJOB_AGENT_BASE_URL`, `HIIJOB_REPORT_AGENT_ID`, `HIIJOB_AGENT_TOKEN`, and timeout settings from env vars. If not configured, it returns deterministic draft placeholders so local tests and demos still work.

- `api/bridge.py`
  FastAPI service exposing health, draft, comment generation, render, card, and download endpoints.

- `ui/streamlit_app.py`
  Optional local/debug UI for uploading a resume, filling fields, and generating a DOCX. It is not the production entry surface.

- `cards/report_review.html`
  Server-rendered review card for consultant confirmation and edits.

- `config/brands/default.yaml`
  Minimal default brand config required for the MVP to run.

- `tests/`
  Unit tests for config loading, validation, service orchestration, Hiijob Agent fallback, API health/draft/render endpoints, and card HTML rendering.

## API Contract Draft

These endpoints will be added to `PRODUCT_SERVICE_CONTRACTS.md` before implementation when the service is integrated under `lobehub/services`.

### `GET /health`

Returns process health and service metadata.

```json
{
  "status": "ok",
  "service": "generic-report-tool",
  "version": "1.0.0"
}
```

### `POST /api/v1/reports/draft`

Creates or updates a report draft from caller-provided context.

Required fields:

- `brand_id`
- `candidate_name`
- `position_title`

Optional fields:

- `resume_text`
- `resume_file_name`
- `job_description`
- `known_fields`
- `source_context`

Response:

```json
{
  "report_id": "report_...",
  "status": "draft",
  "validation": {
    "is_valid": false,
    "missing_items": []
  },
  "card_url": "http://localhost:8767/cards/reports/report_...",
  "render_url": "http://localhost:8767/api/v1/reports/report_.../render"
}
```

### `POST /api/v1/reports/{report_id}/comments`

Generates or regenerates AI recommendation comments for the draft. The first implementation calls `HiijobAgentClient`; the fallback path returns placeholders and missing-information hints.

Optional fields:

- `feedback`
- `sections`
- `known_fields`

### `POST /api/v1/reports/{report_id}/render`

Validates the draft and renders a DOCX artifact. Missing fields are represented as placeholders rather than blocking draft output.

Response:

```json
{
  "report_id": "report_...",
  "status": "confirmed",
  "filename": "default_candidate_report_20260629.docx",
  "download_url": "http://localhost:8767/downloads/default_candidate_report_20260629.docx",
  "missing_information": []
}
```

### `GET /cards/reports/{report_id}`

Returns an HTML review card for Hiijob/LobeHub to show as an openable card. The card includes brand, candidate, position, validation state, editable generated comments, and a render action.

### `GET /downloads/{filename}`

Returns generated artifacts from the configured data directory.

## Hiijob Integration Contract

The Hiijob Report Agent should route "candidate referral report" and "resume recommendation report" tasks to the B9 service. The Agent/MCP layer only needs to:

1. Collect candidate, position, and resume context.
2. Call `POST /api/v1/reports/draft`.
3. Return the `card_url` for consultant review.
4. Optionally call comment regeneration or render endpoints when the user asks from chat.

Codex will not directly edit `federation_gateway/mcp_server.py` or LobeHub Agent DB records. If those changes are required, they should be handed to Claude Code or the owner of Group A with the B9 contract.

## UI Direction

The production interaction is a card, not a full dashboard:

- Header: brand, candidate, position, draft status.
- Left area: required fields and missing information.
- Main area: editable AI recommendation sections.
- Actions: regenerate comments, render DOCX, download generated report.
- Local Streamlit exists only as a development harness.

This keeps the consultant workflow inside Hiijob while preserving service independence.

## Data And Storage

V1 stores draft JSON and generated files under `GENERIC_REPORT_DATA_DIR`, defaulting to `./data`. No candidate data is enriched from external systems inside the service. Any sensitive input is redacted using configured privacy rules before rendering or AI generation where applicable.

## Environment Variables

- `GENERIC_REPORT_CONFIG_DIR`
- `GENERIC_REPORT_TEMPLATE_DIR`
- `GENERIC_REPORT_DATA_DIR`
- `GENERIC_REPORT_PUBLIC_BASE_URL`
- `GENERIC_REPORT_BRIDGE_TOKEN`
- `HIIJOB_AGENT_BASE_URL`
- `HIIJOB_REPORT_AGENT_ID`
- `HIIJOB_AGENT_TOKEN`
- `HIIJOB_AGENT_TIMEOUT`

All credentials and deployment URLs are injected through env vars. No secrets are committed.

## Testing Strategy

Implementation will follow test-first changes for production behavior:

- Config smoke test: default brand loads and validates.
- Validation test: missing required fields produce placeholders.
- Hiijob Agent fallback test: no env config returns deterministic comments.
- Service draft test: draft creation persists a report and returns a card URL.
- Render test: render creates a DOCX file with draft placeholders if required fields are missing.
- API health test: `GET /health` returns service metadata.
- Card test: `GET /cards/reports/{id}` returns HTML containing report context.

Verification commands:

```powershell
python -m py_compile core\config_loader.py core\parser.py core\redactor.py core\prompt_engine.py core\validator.py core\renderer.py core\mcp_server.py
python -m unittest discover -s tests
```

When integrated into Hiijob `services/`, the B-class CI requirement is:

```powershell
python -m unittest discover -s tests
```

## Deployment And Verification

For generic report local development:

```powershell
python api\bridge.py --host 127.0.0.1 --port 8767
```

For Hiijob deployment after files are modified in the relevant Hiijob service paths, use the established one-click deployment flow:

```powershell
.\deploy-to-server.ps1
```

For faster targeted sync when only specific gateway files are changed by the owning agent:

```powershell
.\deploy-to-server.ps1 mcp_server.py intelligence_manager.py
```

The script performs SCP, `docker cp` into both containers, restart, startup wait, and `verify-stack.sh`. For this B9 design, direct changes to A-class gateway files remain out of Codex scope unless explicitly reassigned.

## Scope For MVP

Included:

- Default runnable config.
- B9 service API.
- Hiijob Agent adapter with fallback.
- HTML review card.
- DOCX draft render.
- Local Streamlit debug UI.
- Tests and health endpoint.

Deferred:

- PDF export.
- LLM resume-to-JSON structured parsing.
- Rich visual editing of parsed resume fields.
- Report history list.
- Batch processing.
- Production changes to Group A MCP/Agent routing.

## Risks And Mitigations

- Risk: Hiijob Agent call contract is not yet finalized.
  Mitigation: isolate `HiijobAgentClient` and keep deterministic fallback behavior.

- Risk: Card actions need LobeHub-specific rendering conventions.
  Mitigation: return a plain `card_url` first, matching existing blueprint review card patterns.

- Risk: The generic service drifts into Hiijob-specific assumptions.
  Mitigation: keep brand/template/prompt config in YAML and keep Hiijob as an adapter, not a core dependency.

- Risk: Deployment touches A-class ownership.
  Mitigation: Codex implements B9 and documents the needed Group A handoff instead of editing `federation_gateway/mcp_server.py`.
