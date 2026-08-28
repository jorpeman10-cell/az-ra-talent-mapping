# T-STAR PDF Layout Parse Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make T-STAR DOCX reports preserve wrapped PDF responsibilities, employer/role ownership, achievement text, and education history without replacement-character bullets or fragmented lines.

**Architecture:** Repair PDF extraction artifacts before section classification, then keep company/role inference conservative when a dated line already contains a legal company suffix and a managerial title. Exercise the real parser-to-placeholder-to-DOCX path with a sanitized fixture matching the supplied one-page Chinese resume failure mode.

**Tech Stack:** Python 3, `pypdf`, `python-docx`, `unittest`, existing `core.resume_parser`, `core.placeholder_report`, and `core.renderer` modules.

**Spec:** User-provided source PDF and malformed T-STAR DOCX dated 2026-08-28; root-cause evidence recorded in this task conversation.

## Global Constraints

- Keep comments in English.
- Do not store the candidate's phone number, email address, or full source resume in repository fixtures.
- Preserve the existing T-STAR document visual system and public interfaces.
- Do not modify LobeHub/Federation shared files or deploy production services in this task.
- Use RED -> GREEN and verify the generated DOCX structurally; attempt the canonical DOCX renderer and disclose if LibreOffice is unavailable.

---

### Task 1: Add the real failure-mode regression

**Files:**
- Create: `tests/test_pdf_resume_layout_regression.py`
- Test: `tests/test_pdf_resume_layout_regression.py`

**Interfaces:**
- Consumes: `parse_resume_for_report(text: str) -> dict`, `build_placeholder_context(data: dict, brand_config: dict) -> dict`, and `ReportRenderer.render(data: dict) -> Document`.
- Produces: A regression contract for wrapped PDF bullets, Pfizer multi-role grouping, achievement continuity, education recovery, and clean DOCX text.

- [ ] **Step 1: Write the failing integration test**

```python
def test_wrapped_pdf_resume_keeps_roles_achievements_and_education(self):
    parsed = parse_resume_for_report(SANITIZED_WRAPPED_PDF_TEXT)
    context = build_placeholder_context(
        {"candidate_name": "林然", "resume_text": SANITIZED_WRAPPED_PDF_TEXT, "parsed_resume": parsed},
        {"brand_id": "tstar", "brand_name": "T-STAR", "branding": {}},
    )
    groups = context["appendix_blocks"]["experience_groups"]
    self.assertNotIn("\ufffd", json.dumps(groups, ensure_ascii=False))
    self.assertEqual([role["period"] for role in pfizer["roles"]], ["2018.6- 2020.1", "2004.01- 2018.06"])
    self.assertIn("最高荣誉 2 人次", json.dumps(groups, ensure_ascii=False))
    self.assertIn("复旦大学 2012.6-2015.6", context["appendix_blocks"]["education"])
```

- [ ] **Step 2: Run the new test and verify RED**

Run: `python -m unittest tests.test_pdf_resume_layout_regression -v`

Expected: FAIL because responsibilities remain split, `\ufffd` remains visible, the 2018 title becomes a company bucket, the achievement is cut at `荣誉`, and school/date lines do not pair.

- [ ] **Step 3: Keep the expected values literal and hand-checked**

Assert exact company names, periods, complete responsibility fragments, and education lines. Do not call parser helpers to build expected values.

### Task 2: Repair wrapped PDF lines before section parsing

**Files:**
- Modify: `core/resume_parser.py`
- Test: `tests/test_pdf_resume_layout_regression.py`

**Interfaces:**
- Consumes: raw extracted text passed to `parse_resume_for_report`.
- Produces: normalized text in which a leading `\ufffd` acts as a bullet boundary and continuation lines are joined to the preceding responsibility without changing genuine section/date boundaries.

- [ ] **Step 1: Add a focused normalization helper**

```python
def _repair_wrapped_pdf_lines(text: str) -> str:
    # Convert only line-leading replacement glyphs into a supported bullet.
    # Join non-heading/non-period continuation lines to the current bullet.
    # Keep school lines and employment date lines as independent boundaries.
```

- [ ] **Step 2: Call the helper from `_normalize_resume_text`**

Apply it after encoding repair and before section extraction so `_meaningful_lines` and `_extract_sections` see the same repaired structure.

- [ ] **Step 3: Prevent `荣誉` inside an active responsibility from becoming a section heading**

The repaired line must read `...SG 最高荣誉 2 人次...`; a true standalone `荣誉` heading outside a wrapped responsibility remains a certificate section.

- [ ] **Step 4: Run the regression and verify the line/achievement assertions turn GREEN**

Run: `python -m unittest tests.test_pdf_resume_layout_regression -v`

Expected: Replacement glyph and fragmentation assertions pass; company/role and education assertions may still fail until Task 3.

### Task 3: Harden employer-role and education classification

**Files:**
- Modify: `core/placeholder_report.py`
- Modify: `core/resume_parser.py`
- Test: `tests/test_pdf_resume_layout_regression.py`

**Interfaces:**
- Consumes: repaired experience lines such as `2018.6-2020.1 辉瑞制药有限公司 肿瘤及罕见病全国战略执行经理(RSIM)` and trailing school/date pairs.
- Produces: one `辉瑞制药有限公司` group with both roles, plus combined education entries.

- [ ] **Step 1: Reject managerial titles as suffixless company names**

Extend the suffixless-company guard so Chinese/English role indicators (`经理`, `总监`, `负责人`, `manager`, `director`, and acronym-bearing titles) cannot relocate a dated role into a fake company group.

- [ ] **Step 2: Classify school lines and their immediately following date-only lines as education**

Keep employment periods under experience, but once a school line activates education, attach its next date-only line to education.

- [ ] **Step 3: Pair adjacent school/date education lines for report layout**

Render `复旦大学 2012.6-2015.6` and `中国药科大 1996.09-2000.6` as two coherent lines instead of four detached rows.

- [ ] **Step 4: Run the regression and verify GREEN**

Run: `python -m unittest tests.test_pdf_resume_layout_regression -v`

Expected: PASS with no fake role-named company, no replacement glyph, complete responsibilities, complete achievement text, and two school/date entries.

### Task 4: Verify compatibility and regenerate the sample report

**Files:**
- Modify only if a compatibility regression is found: `core/resume_parser.py`, `core/placeholder_report.py`
- Create output: `output/tstar_candidate_report_parse_fixed_20260828.docx`

**Interfaces:**
- Consumes: the supplied PDF through `extract_resume_text`, `parse_resume_for_report`, and `ReportRenderer`.
- Produces: a corrected DOCX proof artifact and passing project tests.

- [ ] **Step 1: Run focused parser and report tests**

Run: `python -m unittest tests.test_pdf_resume_layout_regression tests.test_config_and_service -v`

Expected: All tests PASS.

- [ ] **Step 2: Run the full test suite**

Run: `python -m unittest discover -s tests -v`

Expected: All tests PASS with no new warnings or errors.

- [ ] **Step 3: Regenerate the supplied sample into a new workspace output file**

Use the original PDF as input, preserve the original report, and write `output/tstar_candidate_report_parse_fixed_20260828.docx`.

- [ ] **Step 4: Audit the DOCX structure**

Verify the DOCX contains exactly one Pfizer employer heading with both periods, contains no `\ufffd`, contains the complete wrapped responsibilities and achievement, and contains both school/date pairs.

- [ ] **Step 5: Attempt canonical render QA**

Run the bundled `render_docx.py` against the regenerated DOCX. If LibreOffice is absent, record the dependency limitation and rely on structural DOCX checks without claiming visual render success.

- [ ] **Step 6: Commit the focused fix**

```bash
git add core/resume_parser.py core/placeholder_report.py tests/test_pdf_resume_layout_regression.py docs/superpowers/plans/2026-08-28-tstar-pdf-layout-parse-hardening.md
git commit -m "fix: harden wrapped PDF resume parsing"
```
