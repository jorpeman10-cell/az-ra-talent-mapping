from __future__ import annotations

import base64
import html
import re
from pathlib import Path
from typing import Any

from .placeholder_report import build_placeholder_context


APPENDIX_FOOTER = (
    "附录提示：原始简历全文仅保留在附录或随报告附件交付。 | "
    "Appendix: the original resume is preserved only in the appendix or as an attached source file."
)


def render_report_html(data: dict[str, Any], brand_config: dict[str, Any]) -> str:
    ctx = build_placeholder_context(data, brand_config)
    profile = _style_profile(ctx["report_style"], brand_config)
    logo_uri = _logo_data_uri()
    experience_groups = ctx["appendix_blocks"].get("experience_groups", [])

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{_escape(ctx["candidate_name"])} - Candidate Referral Report</title>
  <style>
    @page {{ size: A4; margin: 16mm 17mm 18mm; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0 0 18mm;
      background: {profile["page_bg"]};
      color: #111827;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      font-size: 12.2px;
      line-height: 1.56;
    }}
    .page {{
      width: 210mm;
      min-height: 297mm;
      margin: 0 auto 10mm;
      background: #fff;
      padding: 17mm;
      position: relative;
      box-shadow: 0 10px 28px rgba(15, 23, 42, .10);
    }}
    .report-header {{
      display: grid;
      grid-template-columns: 45mm 1fr;
      gap: 9mm;
      align-items: stretch;
      border-bottom: 1.2px solid {profile["primary"]};
      padding-bottom: 8mm;
      margin-bottom: 8mm;
    }}
    .logo-card {{
      border: 1px solid {profile["logo_border"]};
      border-top: 2px solid {profile["primary"]};
      border-radius: 6px;
      background: #fff;
      padding: 6mm 5mm;
      display: grid;
      align-content: center;
      min-height: 36mm;
      box-shadow: inset 0 0 0 1px rgba(214, 161, 0, .10);
    }}
    .logo-card img {{ display: block; width: 34mm; max-width: 100%; margin: 0 auto; }}
    h1 {{ margin: 0 0 4mm; color: {profile["heading"]}; font-size: 25px; line-height: 1.12; letter-spacing: 0; }}
    h2 {{ margin: 7mm 0 3mm; color: {profile["accent"]}; font-size: 16px; line-height: 1.2; letter-spacing: 0; }}
    h3 {{ margin: 0 0 2mm; color: {profile["accent"]}; font-size: 13px; }}
    .meta {{ display: grid; grid-template-columns: 28mm 1fr 28mm 1fr; gap: 3px 8px; }}
    .meta b {{ color: {profile["accent"]}; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ border: 1px solid #d8dee8; padding: 6px 8px; vertical-align: top; }}
    th {{ width: 36mm; color: {profile["accent"]}; text-align: left; font-weight: 700; background: {profile["th_bg"]}; }}
    .candidate-profile-layout.has-photo {{ display: grid; grid-template-columns: 32mm minmax(0, 1fr); gap: 5mm; align-items: stretch; }}
    .candidate-profile-layout.no-photo {{ display: block; }}
    .professional-photo-placeholder {{
      border: 1px dashed {profile["placeholder_border"]};
      background: {profile["placeholder_bg"]};
      min-height: 30mm;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 1.5mm;
      color: {profile["accent"]};
      font-size: 11px;
      line-height: 1.5;
      text-align: center;
    }}
    .photo-avatar-icon {{
      width: 17mm;
      height: 17mm;
      border: 1.5px solid {profile["placeholder_border"]};
      border-radius: 50%;
      position: relative;
      background: #fff;
    }}
    .photo-avatar-icon::before {{
      content: "";
      position: absolute;
      top: 3.2mm;
      left: 5.6mm;
      width: 5.8mm;
      height: 5.8mm;
      border-radius: 50%;
      background: {profile["placeholder_border"]};
    }}
    .photo-avatar-icon::after {{
      content: "";
      position: absolute;
      left: 3.8mm;
      bottom: 3.2mm;
      width: 9.4mm;
      height: 5.2mm;
      border-radius: 7mm 7mm 3mm 3mm;
      background: {profile["placeholder_border"]};
    }}
    .professional-photo {{
      width: 100%;
      height: 38mm;
      display: block;
      object-fit: cover;
      border: 1px solid {profile["logo_border"]};
      background: #fff;
    }}
    .info-grid {{ display: grid; grid-template-columns: 1fr; border: 1px solid #d8dee8; padding: 0; min-width: 0; }}
    .info-row {{ display: grid; grid-template-columns: 32mm minmax(0, 1fr); gap: 6px; padding: 6px 8px; border-bottom: 1px solid #e5e7eb; }}
    .info-row:last-child {{ border-bottom: 0; }}
    .info-row b {{ color: {profile["accent"]}; }}
    .info-row span {{ min-width: 0; overflow-wrap: anywhere; word-break: break-word; }}
    .evidence {{ margin: 0; padding-left: 17px; }}
    .evidence li {{ margin: 0 0 5px; }}
    .section-block {{ padding: 6px 0 8px; border-bottom: 1px solid #d8dee8; break-inside: avoid; }}
    .section-block p {{ margin: 2px 0 3px; }}
    .appendix {{
      overflow-wrap: anywhere;
      word-break: break-word;
      border-top: 2px solid {profile["primary"]};
      padding-top: 5mm;
      font-size: 11.2px;
      line-height: 1.62;
    }}
    .appendix-section {{ margin: 0 0 6mm; break-inside: avoid; }}
    .appendix-section h3 {{ margin: 0 0 2mm; color: {profile["primary"]}; font-size: 13px; }}
    .appendix-info {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 2px 12px; }}
    .language-subheading {{
      margin: 4mm 0 3mm;
      padding-left: 3mm;
      border-left: 2px solid {profile["primary"]};
      color: {profile["accent"]};
      font-size: 13px;
      font-weight: 700;
    }}
    .company-block {{ margin: 0 0 5mm; break-inside: avoid; }}
    .company-name {{ font-weight: 700; color: #111827; margin: 0 0 2mm; }}
    .role-block {{ margin: 0 0 3mm 4mm; }}
    .period {{ font-weight: 700; color: {profile["accent"]}; margin-right: 5px; }}
    .role-title {{ font-weight: 700; color: #374151; }}
    .role-details {{ margin: 1mm 0 0 0; padding-left: 0; list-style: none; }}
    .role-details li {{ margin: 0 0 1mm; }}
    .appendix-footer {{
      position: absolute;
      left: 17mm;
      right: 17mm;
      bottom: 7mm;
      border-top: 1px solid #e5e7eb;
      padding-top: 2mm;
      color: #6b7280;
      font-size: 9.2px;
      text-align: center;
    }}
    .footer {{ margin-top: 10mm; text-align: right; color: #6b7280; font-size: 10.5px; }}
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .page {{ width: auto; min-height: auto; margin: 0; box-shadow: none; page-break-after: always; }}
      .page:last-child {{ page-break-after: auto; }}
    }}
    @media (max-width: 760px) {{
      .page {{ width: auto; min-height: auto; padding: 20px; }}
      .report-header, .meta, .candidate-profile-layout.has-photo, .info-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="report-header">
      <div class="logo-card">{_logo_img(logo_uri)}</div>
      <section>
        <h1>Candidate Referral Report / 候选人推荐报告</h1>
        <div class="meta">
          {_meta_rows([
              ("Candidate", ctx["candidate_name"]),
              ("Target Role", ctx["target_role"]),
              ("Client", ctx["client_company"]),
              ("Current", ctx["current_summary"]),
              ("Salary", ctx["salary_info"]),
          ])}
        </div>
      </section>
    </header>

    <h2>Candidate Profile / 候选人基本信息</h2>
    {_personal_info(ctx)}

    <h2>Recommendation Summary / 推荐摘要</h2>
    {_table([
        ("Motivation / 求职动机", ctx["motivation"]),
        ("Role Fit / 岗位匹配", ctx["role_fit"]),
    ])}

    <h2>Consultant Assessment / 顾问评估</h2>
    {_table([
        ("Strengths / 推荐亮点", ctx["strengths_summary"]),
        ("Risks / Questions / 风险与待确认", ctx["risk_notes"]),
    ])}

    {_work_experience(experience_groups)}

    {_job_description(ctx["job_description"])}

    <div class="footer">Draft for consultant review | {_escape(ctx["brand_name"])} {_escape(ctx["brand_subtitle"])}</div>
    <div class="appendix-footer">{APPENDIX_FOOTER}</div>
  </main>

  <section class="page">
    <h2>Original Resume Appendix / 原始简历附录</h2>
    <div class="appendix">{_appendix(ctx["appendix_blocks"])}</div>
    <div class="appendix-footer">{APPENDIX_FOOTER}</div>
  </section>
</body>
</html>"""


def write_report_html(data: dict[str, Any], brand_config: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report_html(data, brand_config), encoding="utf-8")
    return output


def _style_profile(style: str, brand_config: dict[str, Any]) -> dict[str, str]:
    if style == "consulting_blue":
        return {
            "label": "Consulting Blue",
            "primary": "#0B1F3A",
            "accent": "#1F4E79",
            "heading": "#071A2F",
            "page_bg": "#EEF2F7",
            "th_bg": "#F4F7FB",
            "logo_border": "#CBD5E1",
            "placeholder_border": "#94A3B8",
            "placeholder_bg": "#F8FAFC",
        }
    return {
        "label": "T-STAR Purple Business",
        "primary": "#8F0E5C",
        "accent": "#8F0E5C",
        "heading": "#111827",
        "page_bg": "#F7F3F6",
        "th_bg": "#FDF2F8",
        "logo_border": "#E4C567",
        "placeholder_border": "#D8B4CF",
        "placeholder_bg": "#FDF7FB",
    }


def _logo_data_uri() -> str:
    logo_dir = Path(__file__).parent.parent / "templates" / "tstar"
    logo_path = next(
        (
            path
            for path in (
                logo_dir / "tstar_logo_white.png",
                logo_dir / "tstar_logo_white.jpg",
                logo_dir / "tstar_logo.png",
                logo_dir / "tstar_logo.jpg",
            )
            if path.exists()
        ),
        logo_dir / "tstar_logo.jpg",
    )
    if not logo_path.exists():
        return ""
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    mime = "image/png" if logo_path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{encoded}"


def _logo_img(uri: str) -> str:
    if not uri:
        return '<strong style="font-size:20px">T-STAR 泰伦仕</strong>'
    return f'<img src="{uri}" alt="T-STAR 泰伦仕 logo" />'


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _meta_rows(rows: list[tuple[str, str]]) -> str:
    return "\n".join(f"<b>{_escape(label)}</b><span>{_escape(value or '-')}</span>" for label, value in rows)


def _table(rows: list[tuple[str, str]]) -> str:
    body = "\n".join(
        f"<tr><th>{_escape(label)}</th><td>{_escape(_clean_display_text(value or '-'))}</td></tr>"
        for label, value in rows
    )
    return f"<table>{body}</table>"


def _personal_info(ctx: dict[str, Any]) -> str:
    rows = ctx.get("personal_info_rows") or []
    if not rows:
        rows = [("Name / 姓名", ctx["candidate_name"]), ("Current / 当前", ctx["current_summary"])]
    content = "".join(
        f'<div class="info-row"><b>{_escape(label)}</b><span>{_escape(value)}</span></div>'
        for label, value in rows
    )
    return (
        '<div class="candidate-profile-layout">'
        '<div class="professional-photo-placeholder"><span class="photo-avatar-icon" aria-hidden="true"></span>'
        '<span>职业寸照<br>Professional Photo</span></div>'
        f'<div class="info-grid">{content}</div>'
        '</div>'
    )


def _work_experience(groups: list[dict[str, Any]]) -> str:
    if not groups:
        return ""
    body: list[str] = ["<h2>Work Experience / 工作经历</h2>", '<section class="section-block experience-summary">']
    for heading, section_groups in _bilingual_group_sections(groups):
        if heading:
            body.append(f'<h3 class="language-subheading">{_escape(heading)}</h3>')
        for group in section_groups:
            body.append(_experience_group_html(group, detail_limit=5))
    body.append("</section>")
    return "".join(body)


def _personal_info(ctx: dict[str, Any]) -> str:
    rows = ctx.get("personal_info_rows") or []
    if not rows:
        rows = [("Name / 姓名", ctx["candidate_name"]), ("Current / 当前", ctx["current_summary"])]
    content = "".join(
        f'<div class="info-row"><b>{_escape(label)}</b><span>{_escape(value)}</span></div>'
        for label, value in rows
    )
    photo_uri = str(ctx.get("professional_photo_data_uri") or "")
    photo_required = bool(ctx.get("professional_photo_required"))
    if not photo_uri and not photo_required:
        return f'<div class="candidate-profile-layout no-photo"><div class="info-grid">{content}</div></div>'
    if photo_uri:
        photo = f'<img class="professional-photo" src="{_escape(photo_uri)}" alt="Professional Photo / 职业寸照">'
    else:
        photo = (
            '<div class="professional-photo-placeholder"><span class="photo-avatar-icon" aria-hidden="true"></span>'
            '<span>Photo pending<br>照片待补</span></div>'
        )
    return (
        '<div class="candidate-profile-layout has-photo">'
        f"{photo}"
        f'<div class="info-grid">{content}</div>'
        '</div>'
    )


def _job_description(text: str) -> str:
    if not text:
        return ""
    return f"<h2>Role Requirement Notes / JD 要求</h2>{_table([('JD / 职位需求', text)])}"


def _appendix(blocks: dict[str, Any]) -> str:
    if not blocks:
        return "No original resume text was found. Please re-upload the resume file."
    body: list[str] = []
    personal = blocks.get("personal") or []
    if personal:
        body.append('<section class="appendix-section"><h3>个人信息</h3><div class="appendix-info">')
        for label, value in personal:
            body.append(f"<div><b>{_escape(label)}</b>：{_escape(value)}</div>")
        body.append("</div></section>")
    summary = blocks.get("summary") or []
    if summary:
        body.append('<section class="appendix-section"><h3>自我评价</h3>')
        for item in summary:
            body.append(f"<p>{_escape(item)}</p>")
        body.append("</section>")
    experience_groups = blocks.get("experience_groups") or []
    if experience_groups:
        body.append('<section class="appendix-section"><h3>工作经历</h3>')
        for heading, section_groups in _bilingual_group_sections(experience_groups):
            if heading:
                body.append(f'<h3 class="language-subheading">{_escape(heading)}</h3>')
            for group in section_groups:
                body.append(_experience_group_html(group, detail_limit=50))
        body.append("</section>")
    for title, key in [("教育经历", "education"), ("核心技能", "skills")]:
        items = blocks.get(key) or []
        if items:
            body.append(f'<section class="appendix-section"><h3>{_escape(title)}</h3>')
            for item in items:
                body.append(f"<p>{_escape(item)}</p>")
            body.append("</section>")
    projects = blocks.get("projects") or []
    if projects:
        body.append('<section class="appendix-section"><h3>Project Experience / 项目经历</h3>')
        for item in projects:
            body.append(f"<p>{_escape(item)}</p>")
        body.append("</section>")
    if not body:
        return f"<p>{_escape(blocks.get('fallback') or '')}</p>"
    return "".join(body)


def _experience_group_html(group: dict[str, Any], detail_limit: int) -> str:
    body: list[str] = ['<div class="company-block">']
    body.append(f'<p class="company-name">{_escape(group.get("company", "工作经历"))}</p>')
    for role in group.get("roles", []):
        body.append('<div class="role-block">')
        body.append("<div>")
        body.append(f'<span class="period">{_escape(role.get("period", "-"))}</span>')
        if role.get("title"):
            body.append(f'<span class="role-title">{_escape(role["title"])}</span>')
        body.append("</div>")
        details = role.get("details") or []
        if details:
            body.append('<ul class="role-details">')
            for detail in details[:detail_limit]:
                body.append(f"<li>{_escape(_clean_display_text(detail))}</li>")
            body.append("</ul>")
        body.append("</div>")
    body.append("</div>")
    return "".join(body)


def _bilingual_group_sections(groups: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    english = [group for group in groups if not _group_has_chinese(group)]
    chinese = [group for group in groups if _group_has_chinese(group)]
    if english and chinese:
        return [("English Version", english), ("中文版本", chinese)]
    return [("", groups)]


def _group_has_chinese(group: dict[str, Any]) -> bool:
    probe_parts = [str(group.get("company") or "")]
    for role in group.get("roles", []):
        probe_parts.append(str(role.get("title") or ""))
        probe_parts.extend(str(item) for item in role.get("details", []))
    return bool(re.search(r"[\u4e00-\u9fff]", " ".join(probe_parts)))


def _clean_display_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"(^|\s)[\u2022\u25cf\u25e6\u2219\u26ab]\s*", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()
