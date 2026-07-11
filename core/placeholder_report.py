from __future__ import annotations

import re
from typing import Any

from .resume_parser import resume_sections_from_data, resume_text_from_data, resume_work_experience_from_data


PERSONAL_LABELS = [
    "\u59d3\u540d",
    "Name",
    "\u7535\u8bdd",
    "\u624b\u673a",
    "Phone",
    "Tel",
    "Mobile",
    "\u90ae\u7bb1",
    "\u7535\u5b50\u90ae\u7bb1",
    "Email",
    "E-mail",
    "\u6c11\u65cf",
    "\u51fa\u751f\u5e74\u6708",
    "Date of Birth",
    "DOB",
    "\u6bd5\u4e1a\u9662\u6821",
    "University",
    "School",
    "\u5b66\u5386",
    "Education",
    "\u4e13\u4e1a",
    "Major",
    "\u4f4f\u5740",
    "\u5730\u5740",
    "Address",
    "Location",
]


def _normalize_spaced_personal_labels(text: str) -> str:
    """Normalize labels that DOCX/OCR extraction split with spaces, e.g. 鐢?璇濓細."""
    normalized = str(text or "")
    for label in PERSONAL_LABELS:
        if len(label) < 2:
            continue
        spaced = r"\s*".join(re.escape(char) for char in label)
        normalized = re.sub(rf"{spaced}\s*([:\uff1a])", rf"{label}\1", normalized)
    return normalized

PROFILE_FIELD_RE = re.compile(
    r"^(?:"
    r"\u59d3\u540d|\u7535\u8bdd|\u624b\u673a|\u90ae\u7bb1|\u7535\u5b50\u90ae\u7bb1|"
    r"\u6027\u522b|\u5e74\u9f84|\u6c11\u65cf|\u51fa\u751f\u5e74\u6708|\u6bd5\u4e1a\u9662\u6821|"
    r"\u5b66\u5386|\u5b66\u4f4d|\u4e13\u4e1a|\u4f4f\u5740|\u5730\u5740|\u73b0\u6240\u5728\u5730|"
    r"\u653f\u6cbb\u9762\u8c8c|\u610f\u5411\u5c97\u4f4d|\u6c42\u804c\u610f\u5411|\u671f\u671b\u85aa\u8d44|"
    r"Name|Phone|Tel|Mobile|Cell|Email|E-mail|Gender|Date of Birth|DOB|Address|Location|Title"
    r")\s*[:\uff1a]",
    re.IGNORECASE,
)

PERIOD_RE = re.compile(
    r"(?:19|20)\d{2}(?:[.\-/\u5e74]\d{1,2}\u6708?)?\s*[-~\u2013\u2014\u81f3]+"
    r"\s*(?:\u81f3\u4eca|\u73b0\u5728|present|current|now|(?:19|20)\d{2}(?:[.\-/\u5e74]\d{1,2}\u6708?)?)",
    re.IGNORECASE,
)
MONTH_NAME_RE = re.compile(
    r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?$",
    re.IGNORECASE,
)
MONTH_PERIOD_RE = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+"
    r"(?:19|20)\d{2}\s*[-~\u2013\u2014\u81f3]+\s*"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+)?"
    r"(?:\u81f3\u4eca|\u73b0\u5728|present|current|now|(?:19|20)\d{2})",
    re.IGNORECASE,
)
FLEX_PERIOD_RE = re.compile(
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+)?"
    r"(?:19|20)\d{2}(?:[.\-/\u5e74]\d{1,2}\u6708?)?\s*[-~\u2013\u2014\u81f3]+\s*"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+)?"
    r"(?:\u81f3\u4eca|\u73b0\u5728|present|current|now|(?:19|20)\d{2}(?:[.\-/\u5e74]\d{1,2}\u6708?)?)",
    re.IGNORECASE,
)
ENGLISH_TO_PERIOD_RE = re.compile(
    r"(?:(?:\d{1,2}\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+)?"
    r"(?:19|20)\d{2}\s+to\s+"
    r"(?:(?:\d{1,2}\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+)?"
    r"(?:present|current|now|(?:19|20)\d{2})",
    re.IGNORECASE,
)
PARTIAL_CURRENT_PERIOD_RE = re.compile(
    r"\d{1,2}\s*\u6708\s*[-~\u2013\u2014\u81f3]+\s*(?:\u81f3\u4eca|\u73b0\u5728|present|current|now)",
    re.IGNORECASE,
)


def build_placeholder_context(data: dict[str, Any], brand_config: dict[str, Any]) -> dict[str, Any]:
    rationale = data.get("recommendation_rationale")
    if not isinstance(rationale, dict):
        rationale = {}
    original_resume = resume_text_from_data(data)
    sections = resume_sections_from_data(data)
    appendix_blocks = _appendix_blocks(sections, original_resume)
    report_language = _detect_report_language(data, original_resume)
    salary_info = _salary_summary(data)
    return {
        "brand_id": brand_config.get("brand_id", "default"),
        "brand_name": "T-STAR" if brand_config.get("brand_id") == "tstar" else brand_config.get("brand_name", "Generic Report"),
        "brand_subtitle": "\u6cf0\u4f26\u4ed5" if brand_config.get("brand_id") == "tstar" else "",
        "report_style": _report_style(data),
        "report_language": report_language,
        "candidate_name": _value(data, "candidate_name"),
        "target_role": _value(data, "position_title"),
        "client_company": _value(data, "client_company"),
        "current_company": _value(data, "current_company"),
        "current_title": _value(data, "current_title"),
        "current_summary": _compact_join([data.get("current_title"), data.get("current_company")]) or "-",
        "salary_info": salary_info,
        "motivation": _localized_text(_value(data, "motivation"), report_language),
        "role_fit": _localized_text(_value(data, "role_fit"), report_language),
        "strengths_summary": _localized_text(str(rationale.get("strengths_summary") or "-"), report_language),
        "risk_notes": _localized_text(str(rationale.get("risk_notes") or "-"), report_language),
        "job_description": str(data.get("job_description") or "").strip(),
        "resume_sections": sections,
        "resume_section_blocks": _resume_section_blocks(sections),
        "personal_info_rows": _profile_rows(data, appendix_blocks["personal"]),
        "professional_photo_data_uri": _image_data_uri(data.get("professional_photo_data_uri")),
        "professional_photo_file_name": str(data.get("professional_photo_file_name") or "").strip(),
        "professional_photo_required": _as_bool(
            data.get("professional_photo_required") or data.get("professional_photo_requested")
        ),
        "work_experience_items": resume_work_experience_from_data(data, limit=8),
        "appendix_blocks": appendix_blocks,
        "appendix_resume": _ordered_resume_text(appendix_blocks, original_resume),
        "original_resume": original_resume,
        "placeholder_manifest": {
            "{{brand_name}}": "brand_name",
            "{{candidate_name}}": "candidate_name",
            "{{target_role}}": "target_role",
            "{{client_company}}": "client_company",
            "{{salary_info}}": "salary_info",
            "{{motivation}}": "motivation",
            "{{role_fit}}": "role_fit",
            "{{strengths_summary}}": "strengths_summary",
            "{{risk_notes}}": "risk_notes",
            "{{job_description}}": "job_description",
            "{{resume_sections}}": "resume_section_blocks",
            "{{original_resume}}": "original_resume",
        },
    }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "required", "requested"}


def _resume_section_blocks(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    titles = {
        "personal": "Personal Information / \u4e2a\u4eba\u4fe1\u606f",
        "intention": "Career Intention / \u6c42\u804c\u610f\u5411",
        "summary": "Profile / \u81ea\u6211\u8bc4\u4ef7",
        "experience": "Work Experience / \u5de5\u4f5c\u7ecf\u5386",
        "projects": "Project Experience / \u9879\u76ee\u7ecf\u5386",
        "skills": "Skills / \u6838\u5fc3\u6280\u80fd",
        "education": "Education / \u6559\u80b2\u7ecf\u5386",
        "certificates": "Certificates / \u8bc1\u4e66",
    }
    blocks: list[dict[str, Any]] = []
    for key in ["personal", "intention", "summary", "experience", "projects", "skills", "education", "certificates"]:
        items = _clean_items(sections.get(key, []), limit=30)
        if items:
            blocks.append({"key": key, "title": titles.get(key, key.title()), "items": items})
    return blocks


def _appendix_blocks(sections: dict[str, list[str]], original_resume: str) -> dict[str, Any]:
    personal = _personal_info_from_text(original_resume) or _personal_info_rows_from_sections(sections)
    education = _education_items(sections)
    return {
        "personal": personal,
        "summary": _clean_items(sections.get("summary", []), limit=6),
        "experience_groups": _experience_groups(sections.get("experience", [])),
        "projects": _project_items(sections),
        "education": education,
        "skills": _clean_items(sections.get("skills", []), limit=8),
        "fallback": _dedupe_text(original_resume),
    }


def _personal_info_rows_from_sections(sections: dict[str, list[str]]) -> list[tuple[str, str]]:
    rows_from_text = _personal_info_from_text("\n".join(str(item) for item in sections.get("personal", [])))
    if rows_from_text:
        return rows_from_text
    rows: list[tuple[str, str]] = []
    for item in sections.get("personal", []):
        text = _normalize_spaced_personal_labels(item).strip()
        if "\uff1a" in text:
            label, value = text.split("\uff1a", 1)
        elif ":" in text:
            label, value = text.split(":", 1)
        else:
            continue
        label = label.strip()
        value = value.strip()
        if label and value and len(label) <= 12 and len(value) <= 120:
            rows.append((label, value))
    return rows[:10]


def _personal_info_from_text(text: str) -> list[tuple[str, str]]:
    label_group = "|".join(re.escape(label) for label in PERSONAL_LABELS)
    normalized = _normalize_spaced_personal_labels(text)
    normalized = re.sub(r"\s*\|\s*", "\n", normalized)
    normalized = re.sub(rf"(?<!^)\s*((?:{label_group})\s*[:\uff1a])", r"\n\1", normalized)
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in normalized.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        match = re.match(rf"^({label_group})\s*[:\uff1a]\s*(.+)$", line)
        if not match:
            continue
        label = match.group(1).strip()
        value = match.group(2).strip()
        value = re.split(rf"(?=(?:{label_group})\s*[:\uff1a])", value, maxsplit=1)[0].strip()
        if not value or len(value) > 120 or label in seen:
            continue
        seen.add(label)
        rows.append((label, value))
    if "\u7535\u8bdd" not in seen and "\u624b\u673a" not in seen:
        phone = re.search(r"(?:^|[\s:\uff1a])((?:\+?86[-\s]?)?1[3-9]\d{9})(?:\s|$)", normalized)
        if phone:
            rows.append(("\u7535\u8bdd", phone.group(1).strip()))
            seen.add("\u7535\u8bdd")
    if not any(label.lower() in {"phone", "tel", "mobile"} for label in seen):
        phone = re.search(r"(?:Phone|Tel|Mobile|Cell)\s*[:：]?\s*((?:\+?\d[\d\s().-]{7,}\d))", normalized, re.IGNORECASE)
        if phone:
            rows.append(("Phone", phone.group(1).strip()))
            seen.add("Phone")
    if "\u90ae\u7bb1" not in seen and "\u7535\u5b50\u90ae\u7bb1" not in seen:
        email = re.search(r"[\w.+-]+@[\w.-]+\.\w+", normalized)
        if email:
            rows.append(("\u90ae\u7bb1", email.group(0).strip()))
            seen.add("\u90ae\u7bb1")
    return rows[:10]


def _profile_rows(data: dict[str, Any], parsed_rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    by_label = {str(label).strip(): str(value).strip() for label, value in parsed_rows if str(label).strip() and str(value).strip()}

    def first(*labels: str) -> str:
        for label in labels:
            if by_label.get(label):
                return by_label[label]
        return ""

    rows: list[tuple[str, str]] = []
    used: set[str] = set()

    def add(label: str, value: Any, source_labels: tuple[str, ...] = ()) -> None:
        text = str(value or "").strip()
        if not text:
            return
        key = _normalize_profile_label(label)
        if key in used:
            return
        rows.append((label, text))
        used.add(key)
        for item in source_labels:
            used.add(_normalize_profile_label(item))

    add("Name / 姓名", data.get("candidate_name") or first("姓名", "Name"), ("姓名", "Name"))
    add("Phone / 电话", first("电话", "手机", "Phone", "Tel", "Mobile"), ("电话", "手机", "Phone", "Tel", "Mobile"))
    add("Email / 邮箱", first("邮箱", "电子邮箱", "Email", "E-mail"), ("邮箱", "电子邮箱", "Email", "E-mail"))
    add("Current / 当前", _compact_join([data.get("current_title"), data.get("current_company")]), ())
    add("Birth / 出生年月", first("出生年月", "DOB", "Date of Birth"), ("出生年月", "DOB", "Date of Birth"))
    add("Education / 学历", first("学历", "Education"), ("学历", "Education"))
    add("School / 毕业院校", first("毕业院校", "University", "School"), ("毕业院校", "University", "School"))
    add("Major / 专业", first("专业", "Major"), ("专业", "Major"))
    add("Address / 地址", first("住址", "地址", "Address", "Location"), ("住址", "地址", "Address", "Location"))

    for label, value in parsed_rows:
        normalized = _normalize_profile_label(label)
        if normalized in used:
            continue
        if len(rows) >= 10:
            break
        add(label, value, (label,))
    return rows


def _normalize_profile_label(label: str) -> str:
    return re.sub(r"\s+", "", str(label or "").lower().replace("/", ""))


def _image_data_uri(value: Any) -> str:
    text = str(value or "").strip()
    if re.match(r"^data:image/(?:png|jpe?g|webp);base64,[A-Za-z0-9+/=\s]+$", text, re.IGNORECASE):
        return re.sub(r"\s+", "", text)
    return ""


def _education_items(sections: dict[str, list[str]]) -> list[str]:
    candidates: list[str] = []
    candidates.extend(sections.get("education", []))

    # Some PDF/DOCX extractions place school lines immediately under work
    # history. Keep them in the appendix education block, not experience.
    for item in sections.get("experience", []):
        if _looks_like_education_line(item) or _looks_like_personal_value_line(item):
            candidates.append(item)

    cleaned: list[str] = []
    for item in _clean_items(candidates, limit=40):
        if _looks_like_personal_value_line(item) and not _looks_like_education_line(item):
            continue
        cleaned.append(item)
    return _clean_items(cleaned, limit=12)


def _project_items(sections: dict[str, list[str]]) -> list[str]:
    candidates: list[str] = []
    candidates.extend(sections.get("projects", []))

    experience_items = _clean_items(sections.get("experience", []), limit=260)
    index = 0
    while index < len(experience_items):
        item = experience_items[index]
        if not _looks_like_project_experience_line(item):
            index += 1
            continue

        block: list[str] = [item]
        index += 1
        while index < len(experience_items):
            next_item = experience_items[index]
            if _looks_like_report_artifact_line(next_item):
                index += 1
                continue
            if _looks_like_project_experience_line(next_item) or _looks_like_project_detail_line(next_item):
                block.append(next_item)
                index += 1
                continue
            if _line_is_mostly_period(next_item):
                block.append(next_item)
                index += 1
                continue
            if _extract_company(next_item) or _is_role_heading_line(next_item):
                break
            if _extract_period(next_item) and not _looks_like_project_experience_line(next_item):
                break
            block.append(next_item)
            index += 1
        candidates.append(" ".join(block).strip())

    return _clean_items(
        [
            item for item in candidates
            if (
                not _is_profile_field(str(item))
                and not _looks_like_personal_value_line(str(item))
                and not _looks_like_personal_contamination_line(str(item))
            )
        ],
        limit=12,
    )


def _experience_groups(items: list[str]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    by_company: dict[str, dict[str, Any]] = {}
    current_role: dict[str, Any] | None = None
    current_company = ""
    current_group: dict[str, Any] | None = None
    pending_period = ""

    for item in _prepare_experience_items(items):
        labelled_period = _extract_english_label_value(item, "period")
        if labelled_period:
            pending_period = _extract_period(labelled_period) or labelled_period
            current_role = None
            continue
        labelled_company = _extract_english_label_value(item, "company")
        if labelled_company:
            company = _clean_company_name(labelled_company)
            if company:
                current_company = company
                previous_group = current_group
                previous_role = current_role
                current_group = _get_company_group(groups, by_company, company)
                if pending_period:
                    current_role = {"period": pending_period, "title": "", "details": []}
                    current_group["roles"].append(current_role)
                    pending_period = ""
                elif previous_group is not None and _is_period_only_role(previous_role):
                    try:
                        previous_group["roles"].remove(previous_role)
                    except (AttributeError, ValueError):
                        pass
                    current_role = previous_role
                    current_group["roles"].append(current_role)
                else:
                    current_role = None
            continue
        labelled_title = _extract_english_label_value(item, "title")
        if labelled_title:
            title = _clean_english_title(labelled_title)
            if title:
                group = _get_company_group(groups, by_company, current_company or "\u5de5\u4f5c\u7ecf\u5386")
                current_group = group
                if current_role is None:
                    current_role = {"period": pending_period or "-", "title": "", "details": []}
                    group["roles"].append(current_role)
                    pending_period = ""
                if not current_role.get("title"):
                    current_role["title"] = title
                else:
                    current_role.setdefault("details", []).append(title)
            continue
        if _is_profile_field(item) or _looks_like_education_line(item) or _looks_like_personal_value_line(item):
            continue
        if _looks_like_english_experience_label(item):
            continue
        service_company = _extract_service_company(item)
        if service_company:
            current_company = _clean_company_name(service_company)
            current_group = _get_company_group(groups, by_company, current_company)
            current_role = None
            continue
        service_role = _extract_service_role(item)
        if service_role:
            group = _get_company_group(groups, by_company, current_company or "\u5de5\u4f5c\u7ecf\u5386")
            current_group = group
            current_role = {"period": "-", "title": service_role, "details": []}
            group["roles"].append(current_role)
            continue
        if current_role is not None:
            split_year_title = _extract_pdf_split_year_title(item)
            if split_year_title and _is_partial_current_period(str(current_role.get("period") or "")):
                year, title = split_year_title
                current_role["period"] = _complete_partial_current_period(str(current_role.get("period") or ""), year)
                if title and (not current_role.get("title") or _is_pdf_split_noise_title(str(current_role.get("title")))):
                    current_role["title"] = title
                elif title:
                    current_role.setdefault("details", []).append(title)
                continue
        period = _extract_period(item)
        remainder = item
        if period:
            remainder = remainder.replace(period, "", 1).strip(" -|\uff1a:")
        company = _extract_company(remainder)
        if not company and period:
            inferred_company, inferred_title = _split_english_company_role(remainder)
            if inferred_company:
                company = inferred_company
                remainder = inferred_title
        if not company and period:
            inferred_company, inferred_title, inferred_detail = _split_suffixless_company_role(remainder)
            if inferred_company:
                company = inferred_company
                remainder = " ".join(part for part in [inferred_title, inferred_detail] if part).strip()
            elif _looks_like_english_company_name(remainder):
                company = remainder
                remainder = ""
            elif _looks_like_suffixless_company_name(remainder):
                company = remainder
                remainder = ""
        if not company and not period and (_looks_like_suffixless_company_name(remainder) or _looks_like_english_company_name(remainder)):
            company = remainder
        if company:
            original_company = company
            company = _clean_company_name(company)
            remainder = remainder.replace(original_company, "", 1).strip(" -|\uff1a:")
            current_company = company
            previous_group = current_group
            target_group = _get_company_group(groups, by_company, company)
            if current_role is not None and previous_group is not None and _should_move_role_to_following_company(current_role, previous_group):
                try:
                    previous_group["roles"].remove(current_role)
                except ValueError:
                    pass
                if _is_placeholder_role(current_role):
                    current_role = None
                else:
                    target_group["roles"].append(current_role)
                    current_group = target_group
            else:
                current_group = target_group

        if period:
            group = _get_company_group(groups, by_company, current_company or company or "\u5de5\u4f5c\u7ecf\u5386")
            current_group = group
            current_role = {"period": period, "title": "", "details": []}
            if remainder:
                if _looks_like_compact_period_title(remainder):
                    title, detail = remainder, ""
                else:
                    title, detail = _split_role_title_and_detail(remainder)
                current_role["title"] = title
                if detail:
                    current_role["details"].append(detail)
            group["roles"].append(current_role)
            continue

        if company and not remainder:
            current_role = None
            continue

        if company and current_role is None:
            group = _get_company_group(groups, by_company, company)
            current_group = group
            current_role = {"period": "-", "title": "", "details": []}
            group["roles"].append(current_role)
            if remainder:
                title, detail = _split_role_title_and_detail(remainder)
                current_role["title"] = title
                if detail:
                    current_role["details"].append(detail)
            continue

        if not current_role:
            group = _get_company_group(groups, by_company, current_company or "\u5de5\u4f5c\u7ecf\u5386")
            current_group = group
            current_role = {"period": "-", "title": "", "details": []}
            group["roles"].append(current_role)

        if remainder and remainder != current_company:
            if not current_role.get("title"):
                title, detail = _split_role_title_and_detail(remainder)
                if title:
                    current_role["title"] = title
                    if detail:
                        current_role.setdefault("details", []).append(detail)
                    continue
            if not current_role.get("title") and _looks_like_role_title(remainder):
                current_role["title"] = remainder
            else:
                current_role.setdefault("details", []).append(remainder)

    groups = _relocate_misplaced_company_roles(groups, by_company)
    groups = [group for group in groups if group.get("roles") and not _looks_like_education_line(str(group.get("company") or ""))]
    for group in groups:
        for role in group["roles"]:
            role["details"] = _clean_items(
                [
                    item for item in role.get("details", [])
                    if (
                        not _is_profile_field(str(item))
                        and not _looks_like_education_line(str(item))
                        and not _looks_like_personal_contamination_line(str(item))
                        and not _looks_like_project_detail_line(str(item))
                        and not _looks_like_project_experience_line(str(item))
                    )
                ],
                limit=10,
            )
        group["roles"] = _dedupe_roles_by_period(group["roles"])
        group["roles"] = _demote_untitled_short_roles(group["roles"])
        group["roles"] = _drop_noise_placeholder_roles(group["roles"])
        group["roles"] = _filter_company_role_mismatches(str(group.get("company") or ""), group["roles"])
        group["roles"].sort(key=_role_sort_key, reverse=True)
    groups = [group for group in groups if group.get("roles")]
    groups.sort(key=_group_sort_key, reverse=True)
    return groups


def _filter_company_role_mismatches(company: str, roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for role in roles:
        text = " ".join(
            [str(role.get("title") or ""), *[str(item) for item in role.get("details", [])]]
        )
        if re.search(r"\u533b\u9662", company):
            period = str(role.get("period") or "")
            if _period_sort_key(period)[1] >= 202001:
                continue
            role["details"] = [
                detail for detail in role.get("details", [])
                if not re.search(r"\u51cf\u91cd|\u79d1\u666e|\u516c\u4f17\u53f7|\u533b\u5b66\u9879\u76ee|\u5ba2\u6237\u9700\u6c42|\u9605\u8bfb\u91cf|\u5185\u5bb9\u4ea7\u54c1|\u4e01\u9999\u56ed|\u5b66\u672f\u5f71\u54cd\u529b|\u8425\u9500\u7b56\u7565", str(detail))
            ]
            text = " ".join([str(role.get("title") or ""), *[str(item) for item in role.get("details", [])]])
            if re.search(r"\u51cf\u91cd|\u79d1\u666e|\u516c\u4f17\u53f7|\u533b\u5b66\u9879\u76ee|\u5ba2\u6237\u9700\u6c42|\u9605\u8bfb\u91cf|\u5185\u5bb9\u4ea7\u54c1|\u4e01\u9999\u56ed", text):
                continue
        result.append(role)
    return result


def _extract_english_label_value(text: str, kind: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip(" -|\uff1a:"))
    patterns = {
        "period": r"^(?:Period|Date of Employment|Duration|Employment Period|Month/Year)\s*[:\uff1a]\s*(.+)$",
        "company": r"^(?:Employer|Company|Name of Employer)\s*[:\uff1a]\s*(.+)$",
        "title": r"^(?:Job Title(?:\s*&\s*Function)?|Position|Title|Business Title)\s*[:\uff1a]\s*(.+)$",
    }
    pattern = patterns.get(kind)
    if not pattern:
        return ""
    match = re.match(pattern, value, re.IGNORECASE)
    if not match:
        return ""
    result = match.group(1).strip(" -|\uff1a:")
    if kind == "company" and (_looks_like_english_resume_fragment(result) or _looks_like_role_title(result)):
        return ""
    return result


def _is_period_only_role(role: dict[str, Any] | None) -> bool:
    if not role:
        return False
    period = str(role.get("period") or "").strip()
    title = str(role.get("title") or "").strip()
    details = [str(item).strip() for item in role.get("details", []) if str(item).strip()]
    return bool(period and period != "-" and not title and not details)


def _looks_like_english_experience_label(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "").strip(" -|\uff1a:"))
    return bool(
        re.fullmatch(
            r"(?:Main Responsibilities|Responsibilities|Key Responsibilities|Key Accountability|"
            r"Achievements?|Report to|Reports to|Line Manager|Department|Function)",
            value,
            re.IGNORECASE,
        )
    )


def _clean_company_name(company: str) -> str:
    value = re.sub(r"\s+", " ", str(company or "").strip(" -|\uff1a:"))
    if not value:
        return ""
    if re.search(r"[\u4e00-\u9fff]", value):
        return value
    value = re.sub(
        r"\s*/\s*(?:Beijing|Shanghai|Guangzhou|Shenzhen|Nanjing|Hangzhou|Suzhou|Chengdu|China|P\.?R\.?\s*China)\b.*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r",\s*(?:Beijing|Shanghai|Guangzhou|Shenzhen|Nanjing|Hangzhou|Suzhou|Chengdu|China|P\.?R\.?\s*China)\b.*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip(" -|,")


def _clean_english_title(title: str) -> str:
    value = re.sub(r"\s+", " ", str(title or "").strip(" -|\uff1a:"))
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value).strip()
    return value


def _drop_noise_placeholder_roles(roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has_dated_role = any(str(role.get("period") or "").strip() not in {"", "-"} for role in roles)
    if not has_dated_role:
        return roles
    result: list[dict[str, Any]] = []
    for role in roles:
        period = str(role.get("period") or "").strip()
        title = str(role.get("title") or "").strip()
        details = " ".join(str(item).strip() for item in role.get("details", []) if str(item).strip())
        if period and period != "-" and title and not details and len(title) <= 12 and not _looks_like_role_title(title):
            continue
        if period in {"", "-"} and not title and _looks_like_summary_fragment(details):
            continue
        if period in {"", "-"} and not title and _looks_like_project_detail_line(details):
            continue
        if period in {"", "-"} and not title and re.search(r"\u7d2f\u8ba1\u4e3b\u5bfc|\u5934\u90e8\u836f\u4f01|\u533b\u5b66\u63a8\u5e7f\u9879\u76ee", details):
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", title) and re.search(r"现居地|手机|电话|邮箱", details):
            continue
        result.append(role)
    return result


def _looks_like_summary_fragment(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    return bool(
        re.search(
            r"\b(?:experience spanning|specialize in|recognized for|profile|self-evaluation|"
            r"\d+\+?\s*yrs?\s+working|organization development|distribution management)\b",
            value,
            re.IGNORECASE,
        )
    )


def _looks_like_compact_period_title(text: str) -> bool:
    value = str(text or "").strip()
    if not value or len(value) > 90:
        return False
    if re.search(r"[:\uff1a]", value):
        return False
    if re.search(r"[\u3002\uff1b;]|\d+%|\u8fbe\u6210|\u589e\u957f|\u4fdd\u7559", value):
        return False
    if re.match(
        r"^(?:\u8d1f\u8d23|\u5236\u5b9a|\u5efa\u7acb|\u9886\u5bfc|\u627f\u63a5|\u4e3b\u5bfc|\u63a8\u52a8|\u5168\u9762|"
        r"Lead|Develop|Build|Manage|Provide|Execute|Coordinate)\b",
        value,
        re.IGNORECASE,
    ):
        return False
    return True


def _should_move_role_to_following_company(role: dict[str, Any], group: dict[str, Any]) -> bool:
    if _is_generic_company(str(group.get("company", ""))):
        return True
    period = str(role.get("period") or "").strip()
    title = str(role.get("title") or "").strip()
    details = " ".join(str(item).strip() for item in role.get("details", []) if str(item).strip())
    return period not in {"", "-"} and not title and bool(re.search(r"\breport to\b|^\s*$", details, re.IGNORECASE))


def _prepare_experience_items(items: list[str]) -> list[str]:
    raw_items = [
        item for item in _clean_items(items, limit=260)
        if (
            not _is_profile_field(item)
            and not _looks_like_personal_value_line(item)
            and not _looks_like_report_artifact_line(item)
            and not _looks_like_project_detail_line(item)
        )
    ]
    result: list[str] = []
    index = 0
    while index < len(raw_items):
        item = raw_items[index]
        if re.fullmatch(r"(?:Period|Date of Employment|Duration|Employment Period|Month/Year)\s*[:\uff1a]?", item, re.IGNORECASE):
            next_item = raw_items[index + 1] if index + 1 < len(raw_items) else ""
            period = _extract_period(next_item)
            if period and _line_is_mostly_period(next_item):
                result.append(f"Period: {period}")
                index += 2
                continue
        if result and re.fullmatch(r"(?:Ltd\.?|Inc\.?|Co\.?|KG|ApS|GmbH)", item, re.IGNORECASE):
            result[-1] = f"{result[-1].rstrip(' .,')} {item}".strip()
            index += 1
            continue
        if _looks_like_project_experience_line(item):
            index = _skip_project_experience_block(raw_items, index)
            continue

        if (
            _is_location_only_line(item)
            or _looks_like_report_artifact_line(item)
            or _looks_like_project_detail_line(item)
        ):
            index += 1
            continue

        if _can_be_preperiod_title(item):
            consumed, combined = _combine_following_period(item, raw_items, index)
            if combined:
                result.append(combined)
                index += consumed
                continue

        if _is_role_heading_line(item):
            consumed, combined = _combine_following_period(item, raw_items, index)
            if combined:
                result.append(combined)
                index += consumed
                continue

        result.append(item)
        index += 1
    return _clean_items(
        [
            item for item in result
            if (
                not _looks_like_report_artifact_line(item)
                and not _looks_like_project_experience_line(item)
                and not _looks_like_project_detail_line(item)
            )
        ],
        limit=240,
    )


def _can_be_preperiod_title(text: str) -> bool:
    value = str(text or "").strip()
    if not value or _extract_period(value) or _extract_company(value):
        return False
    if _looks_like_education_line(value) or _looks_like_english_resume_fragment(value):
        return False
    if re.search(r"[:\uff1a]$", value):
        return False
    return len(value) <= 90


def _combine_following_period(title: str, items: list[str], index: int) -> tuple[int, str]:
    title_value = title.strip()
    trailing_month = _trailing_month(title_value)
    if trailing_month:
        title_value = title_value[: -len(trailing_month)].strip(" -|")
        next_line = items[index + 1] if index + 1 < len(items) else ""
        period = _period_from_parts(trailing_month, next_line)
        if period:
            return 2, f"{period} {title_value}".strip()

    next_line = items[index + 1] if index + 1 < len(items) else ""
    next_next = items[index + 2] if index + 2 < len(items) else ""
    third = items[index + 3] if index + 3 < len(items) else ""

    if MONTH_NAME_RE.fullmatch(next_line.strip()):
        period = _period_from_parts(next_line, next_next, third)
        if period:
            consumed = 4 if third and period.endswith(third.strip()) else 3
            return consumed, f"{period} {title_value}".strip()

    period = _extract_period(next_line)
    if period and _line_is_mostly_period(next_line):
        remainder = next_line.replace(period, "", 1).strip(" -|\uff1a:")
        return 2, " ".join(part for part in [period, title_value, remainder] if part).strip()
    return 0, ""


def _skip_project_experience_block(items: list[str], index: int) -> int:
    index += 1
    while index < len(items):
        item = items[index]
        if _looks_like_report_artifact_line(item):
            index += 1
            continue
        if _looks_like_project_experience_line(item) or _looks_like_project_detail_line(item) or _line_is_mostly_period(item):
            index += 1
            continue
        if _extract_company(item):
            break
        if _is_role_heading_line(item) and not _looks_like_project_detail_line(item):
            break
        if _extract_period(item) and not _looks_like_project_experience_line(item):
            break
        index += 1
    return index


def _period_from_parts(month: str, start_line: str, end_line: str = "") -> str:
    month = month.strip()
    start = start_line.strip()
    end = end_line.strip()
    if not month or not start:
        return ""
    if re.match(r"^(?:19|20)\d{2}\s*[-~\u2013\u2014\u81f3]+\s*$", start) and end:
        candidate = f"{month} {start} {end}"
    else:
        candidate = f"{month} {start}"
    return _extract_period(candidate)


def _trailing_month(text: str) -> str:
    match = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s*$", text, re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _is_role_heading_line(text: str) -> bool:
    value = str(text or "").strip()
    if not value or _extract_company(value) or _extract_period(value):
        return False
    if _looks_like_education_line(value) or _looks_like_english_resume_fragment(value):
        return False
    if re.search(r"[:\uff1a]$", value):
        return False
    if re.search(r"[\u4e00-\u9fff]", value) and len(value) <= 60:
        return not _looks_like_detail(value)
    return _looks_like_role_title(value) or _looks_like_english_role_title(value) or bool(
        re.search(r"\b(?:sales|retail|account|business development|supervisor|trainee|director|manager)\b", value, re.IGNORECASE)
    )


def _is_location_only_line(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    return bool(
        re.fullmatch(
            r"(?:Beijing|Shanghai|Nanjing|Ithaca|New York|China|US|USA|"
            r"(?:Beijing|Shanghai|Nanjing|Ithaca|New York),\s*(?:China|US|USA)|"
            r"徐州/北京|北京|上海|广州|杭州|深圳|南京|成都|苏州|徐州)",
            value,
            re.IGNORECASE,
        )
    )


def _looks_like_report_artifact_line(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "").strip(" -|\uff1a:"))
    if not value:
        return False
    normalized = re.sub(r"[\s/|:：_-]+", "", value).lower()
    if normalized in {
        "recommendationsummary推荐摘要",
        "consultantassessment顾问评估",
        "originalresumeappendix原始简历附录",
        "candidateprofile候选人基本信息",
        "parsedresume简历原文",
        "resumeevidence简历证据",
    }:
        return True
    return bool(re.search(r"^(?:Recommendation Summary|Consultant Assessment|Original Resume Appendix|Resume Evidence)\b", value, re.IGNORECASE))


def _looks_like_project_experience_line(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "").strip(" -|\uff1a:"))
    if not value:
        return False
    if re.fullmatch(r"(?:项目经历|项目经验|项目成果|荣誉|荣誉证书|荣获公司)", value):
        return True
    if re.search(r"(?:项目成果|荣获公司“|医学科普|书籍科普|学习加速营|公众号品牌传播)", value):
        return True
    if not _extract_period(value):
        return False
    if _extract_company(value):
        return False
    return bool(re.search(r"(?:项目策划|项目管理|项目经理|项目成果|书籍科普|公众号品牌传播|学习加速营|医学科普内容策划)", value))


def _looks_like_project_detail_line(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "").strip(" -|\uff1a:"))
    if not value:
        return False
    return bool(
        re.search(
            r"(?:【项目成果】|医学科普|患者教育内容|公众号|医生用户|原创医学插画|闯关打卡|"
            r"内容规划|选题|粉丝互动|阅读量|私域|品牌声量|社会热点|条漫|文献解读|"
            r"图文素材|活动预热|客户需求及产品)",
            value,
        )
    )


def _line_is_mostly_period(text: str) -> bool:
    period = _extract_period(text)
    if not period:
        return False
    rest = str(text).replace(period, "", 1).strip(" -|")
    return len(rest) <= 8


def _relocate_misplaced_company_roles(
    groups: list[dict[str, Any]],
    by_company: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    for group in list(groups):
        source_company = str(group.get("company") or "")
        kept_roles: list[dict[str, Any]] = []
        for role in group.get("roles", []):
            title = str(role.get("title") or "").strip()
            if _looks_like_suffixless_company_name(title) and title != source_company:
                role["title"] = ""
                _promote_leading_detail_role(role)
                target_group = _get_company_group(groups, by_company, title)
                target_group["roles"].append(role)
            else:
                kept_roles.append(role)
        group["roles"] = kept_roles
    return groups


def _promote_leading_detail_role(role: dict[str, Any]) -> None:
    if str(role.get("title") or "").strip():
        return
    details = [str(item).strip() for item in role.get("details", []) if str(item).strip()]
    if not details:
        return
    title, detail = _split_leading_role_title(details[0])
    if not title:
        return
    role["title"] = title
    role["details"] = ([detail] if detail else []) + details[1:]


def _dedupe_roles_by_period(roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_period: dict[str, dict[str, Any]] = {}
    for role in roles:
        period = str(role.get("period") or "-").strip()
        period_key = _normalize_period_key(period)
        if not period_key or period_key == "-":
            result.append(role)
            continue
        existing = by_period.get(period_key)
        if existing is None:
            by_period[period_key] = role
            result.append(role)
            continue
        title = str(role.get("title") or "").strip()
        existing_title = str(existing.get("title") or "").strip()
        if title and not existing_title:
            existing["title"] = title
        elif title and title not in existing_title:
            existing["details"] = [title, *existing.get("details", [])]
        existing["details"] = _clean_items([*existing.get("details", []), *role.get("details", [])], limit=12)
    return result


def _demote_untitled_short_roles(roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for role in roles:
        period = str(role.get("period") or "").strip()
        title = str(role.get("title") or "").strip()
        details = [str(item).strip() for item in role.get("details", []) if str(item).strip()]
        if result and period not in {"", "-"} and not title and 1 <= len(details) <= 2:
            merged_detail = " ".join([period, *details]).strip()
            previous = result[-1]
            previous["details"] = _clean_items([*previous.get("details", []), merged_detail], limit=12)
            continue
        result.append(role)
    return result


def _normalize_period_key(period: str) -> str:
    value = re.sub(r"\s+", "", str(period or "").lower())
    value = re.sub(r"[\u2013\u2014~]+", "-", value)
    value = value.replace("--", "-")
    value = re.sub(r"(?:\u73b0\u5728|present|current)$", "\u81f3\u4eca", value)
    return value.strip("-")


def _role_sort_key(role: dict[str, Any]) -> tuple[int, int]:
    return _period_sort_key(str(role.get("period") or ""))


def _group_sort_key(group: dict[str, Any]) -> tuple[int, int]:
    roles = group.get("roles") or []
    if not roles:
        return (0, 0)
    return max(_role_sort_key(role) for role in roles)


def _period_sort_key(period: str) -> tuple[int, int]:
    value = str(period or "").lower()
    if re.search(r"\u81f3\u4eca|\u73b0\u5728|present|current", value):
        end_key = 999912
    else:
        matches = _period_date_parts(value)
        if not matches:
            return (0, 0)
        end_year, end_month = matches[-1]
        end_key = int(end_year) * 100 + int(end_month or 12)

    matches = _period_date_parts(value)
    start_key = 0
    if matches:
        start_key = int(matches[0][0]) * 100 + int(matches[0][1] or 1)
    return (end_key, start_key)


def _period_date_parts(value: str) -> list[tuple[str, int]]:
    month_lookup = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    parts: list[tuple[str, int]] = []
    token_re = re.compile(
        r"(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+)?"
        r"((?:19|20)\d{2})(?:[.\-/\u5e74]\s*(\d{1,2}))?",
        re.IGNORECASE,
    )
    for match in token_re.finditer(str(value or "")):
        month_name = (match.group(1) or "").lower()
        month = int(match.group(3) or 0)
        if not month and month_name:
            month = month_lookup.get(month_name, 0)
        parts.append((match.group(2), month))
    return parts


def _split_role_title_and_detail(text: str) -> tuple[str, str]:
    value = str(text or "").strip()
    if not value:
        return "", ""
    if _looks_like_english_role_title(value):
        return value, ""
    leading_title, leading_detail = _split_leading_role_title(value)
    if leading_title and leading_detail:
        return leading_title, leading_detail
    if re.search(r"[\u4e00-\u9fff]", value) and len(value) <= 60 and not re.search(r"[:\uff1a]", value) and not _looks_like_detail(value):
        return value, ""
    pieces = re.split(r"\s+", value, maxsplit=1)
    first = pieces[0].strip()
    rest = pieces[1].strip() if len(pieces) > 1 else ""
    if _looks_like_role_title(first):
        return first, rest
    if re.search(r"[\u4e00-\u9fff]", first) and len(first) <= 30 and not _looks_like_detail(first):
        return first, rest
    return "", value


def _looks_like_role_title(text: str) -> bool:
    value = str(text or "").strip()
    if _looks_like_english_role_title(value):
        return True
    return bool(
        re.fullmatch(
            r"\u9ad8\u7ea7\u5730\u533a\u7ecf\u7406|\u5730\u533a\u7ecf\u7406|S,?\s*MR|"
            r"\u4ea7\u54c1\u7814\u53d1|\u5e02\u573a\u63a8\u5e7f\s*\u7ecf\u7406|\u5e02\u573a\u63a8\u5e7f|"
            r"\u4ea7\u54c1\u7ecf\u7406|\u9500\u552e\u7ecf\u7406|\u4ee3\u8868|\u7ecf\u7406|"
            r"manager|director|representative",
            value,
            re.IGNORECASE,
        )
    )


def _looks_like_english_role_title(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "").strip(" -|\uff1a:"))
    if not value or len(value) > 90:
        return False
    if re.search(r"[:\uff1a]", value):
        return False
    if re.search(r"^(?:report to|main responsibilities|responsibilities)\b", value, re.IGNORECASE):
        return False
    if re.search(r"\b(?:lead|provide|build|achieve|turnover|working|training|consumables|company)\b", value, re.IGNORECASE):
        return False
    return bool(re.search(r"\b(?:manager|director|representative|supervisor|trainee|assistant|associate|head|lead|vp|president|surgeon|physician|doctor)\b", value, re.IGNORECASE))


def _split_leading_role_title(text: str) -> tuple[str, str]:
    value = str(text or "").strip()
    role_pattern = (
        r"\u9ad8\u7ea7\u5730\u533a\u7ecf\u7406|\u5730\u533a\u7ecf\u7406|S,?\s*MR|"
        r"\u4ea7\u54c1\u7814\u53d1|\u5e02\u573a\u63a8\u5e7f\s*\u7ecf\u7406|\u5e02\u573a\u63a8\u5e7f|"
        r"\u4ea7\u54c1\u7ecf\u7406|\u9500\u552e\u7ecf\u7406|\u4ee3\u8868|\u7ecf\u7406|"
        r"manager|director|representative"
    )
    match = re.match(rf"^({role_pattern})\s*(.*)$", value, re.IGNORECASE)
    if not match:
        return "", value
    return match.group(1).strip(), match.group(2).strip()


def _split_suffixless_company_role(text: str) -> tuple[str, str, str]:
    value = str(text or "").strip()
    if not value:
        return "", "", ""
    if _looks_like_english_role_title(value):
        return "", "", ""
    if re.search(r"客户经理|重点客户|销售总监|业务事业部\s*总经理|区域销售总监|管理培训生", value):
        return "", "", ""
    role_pattern = (
        r"\u9ad8\u7ea7\u5730\u533a\u7ecf\u7406|\u5730\u533a\u7ecf\u7406|S,?\s*MR|"
        r"\u4ea7\u54c1\u7814\u53d1|\u5e02\u573a\u63a8\u5e7f\s*\u7ecf\u7406|\u5e02\u573a\u63a8\u5e7f|"
        r"\u4ea7\u54c1\u7ecf\u7406|\u9500\u552e\u7ecf\u7406|\u4ee3\u8868|\u7ecf\u7406|"
        r"manager|director|representative"
    )
    match = re.search(rf"^(.{{2,24}}?)\s+({role_pattern})(?:\s+(.+))?$", value, re.IGNORECASE)
    if not match:
        return "", "", ""
    company = re.sub(r"\s+", " ", match.group(1)).strip(" -|\uff1a:")
    title = re.sub(r"\s+", " ", match.group(2)).strip()
    detail = re.sub(r"\s+", " ", match.group(3) or "").strip()
    if _is_generic_company(company) or PROFILE_FIELD_RE.match(company) or _looks_like_english_resume_fragment(company):
        return "", "", ""
    return company, title, detail


def _split_english_company_role(text: str) -> tuple[str, str]:
    value = re.sub(r"\s+", " ", str(text or "").strip(" -|\uff1a:"))
    if not value or re.search(r"[\u4e00-\u9fff]", value):
        return "", ""
    match = re.match(r"^(.+\b(?:Hospital))\s+(.+)$", value, re.IGNORECASE)
    if not match:
        return "", ""
    company = match.group(1).strip(" -|,")
    title = match.group(2).strip(" -|,")
    if not _looks_like_english_company_name(company):
        return "", ""
    if not (_looks_like_english_role_title(title) or _looks_like_role_title(title)):
        return "", ""
    return company, title


def _looks_like_suffixless_company_name(text: str) -> bool:
    value = re.sub(r"\s+", "", str(text or "").strip(" -|\uff1a:"))
    if not (2 <= len(value) <= 24):
        return False
    if PROFILE_FIELD_RE.match(value) or _is_generic_company(value):
        return False
    if _looks_like_business_object_not_company(value):
        return False
    if _looks_like_role_title(value) or _looks_like_detail(value):
        return False
    if _looks_like_education_line(value):
        return False
    return bool(
        re.search(
            r"\u533b\u836f|\u836f\u4e1a|\u533b\u7597|\u5236\u836f|\u751f\u7269|\u79d1\u6280|\u533b\u9662|\u6c11\u751f|"
            r"\u8bfa\u548c\u8bfa\u5fb7|\u963f\u65af\u5229\u5eb7|\u8f89\u745e|\u6768\u68ee|\u96c0\u5de2|\u9ad8\u9732\u6d01|"
            r"[（(][A-Za-z][A-Za-z .,&-]+[)）]",
            value,
        )
    )


def _looks_like_business_object_not_company(text: str) -> bool:
    value = re.sub(r"\s+", "", str(text or "").strip(" -|\uff1a:"))
    if not value:
        return False
    if value in {"\u533b\u836f\u5065\u5eb7", "\u533b\u7597\u5065\u5eb7", "\u533b\u836f\u4e8b\u4e1a\u90e8", "\u533b\u7597\u4e8b\u4e1a\u90e8"}:
        return True
    if re.search(r"^(?:\u5bf9\u63a5|\u64c5\u957f|\u7ef4\u62a4|\u5efa\u7acb|\u4e3b\u5bfc|\u8d1f\u8d23|\u63a8\u52a8|\u534f\u540c|\u62d3\u5c55|\u8986\u76d6|\u5236\u5b9a)", value):
        return True
    if re.search(
        r"\u6838\u5fc3\u533b\u9662|\u4e09\u7532\u533b\u9662|\u91cd\u70b9\u533b\u9662|\u533a\u57df\u533b\u9662|"
        r"\u57fa\u5c42\u533b\u7597|\u533b\u9662\u51c6\u5165|\u533b\u9662\u5b9a\u671f|\u533b\u7597\u6e20\u9053|"
        r"\u5ba2\u6237\u8d44\u6e90|\u8d44\u6e90\u7ef4\u62a4",
        value,
    ):
        return True
    if re.search(r"\u8fbe\u6210|\u8fbe\u6210|\u589e\u957f|\u4fdd\u7559|\u51c6\u5165|\u63a8\u5e7f|\u7ef4\u62a4|\u7b56\u7565|\u56e2\u961f|\u6e20\u9053|\u5ba2\u6237|\u8d44\u6e90", value) and re.search(r"\u533b\u9662|\u533b\u7597|\u4ea7\u54c1|\u5e02\u573a", value):
        return True
    return False


def _looks_like_english_company_name(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "").strip(" -|\uff1a:"))
    if not (4 <= len(value) <= 90) or re.search(r"[\u4e00-\u9fff]", value):
        return False
    if _looks_like_english_resume_fragment(value) or _looks_like_role_title(value):
        return False
    if re.search(
        r"^(?:report to|main responsibilities|achievements|languages|education|curriculum vitae|"
        r"employment history|clinical trial experience|therapeutic area expertise|project type|summary|"
        r"senior medical science liaison|medical science liaison|medical advisor|product manager|project manager)\b",
        value,
        re.IGNORECASE,
    ):
        return False
    if not re.search(r"\b(?:ltd|limited|co\.?|company|pharmaceutical|biopharma|biotechnology|technologies|hospital|university|gmbh|aps|inc\.?)\b", value, re.IGNORECASE):
        if re.search(r"\b(?:manager|director|specialist|advisor|liaison|scientist|representative|lead|head|consultant|physician|surgeon|doctor)\b", value, re.IGNORECASE):
            return False
    if re.search(r"\b(?:technologies|olympus|radiometer|sarstedt|biom[\u00e9e]rieux|gmbh|aps|ltd|co\.|office|hospital)\b", value, re.IGNORECASE):
        return True
    words = re.findall(r"[A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff]+", value)
    return 1 <= len(words) <= 4 and sum(1 for word in words if word[:1].isupper()) >= 2


def _looks_like_english_resume_fragment(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "").strip(" -|\uff1a:"))
    value = re.sub(r"^\d+\s*[\).]\s*", "", value)
    value = re.sub(r"^[•▪■◦‣⁃\-\*\uf06e\uf0d8\uf0b7]+\s*", "", value)
    if not value or re.search(r"[\u4e00-\u9fff]", value):
        return False
    compact = re.sub(r"\s+", "", value).lower()
    if re.search(r"_[0-9]{1,2}[a-z]{3}[0-9]{4}$", compact):
        return True
    return bool(
        re.search(
            r"^(?:and|to|work in|report to|turnover|new application|be in charge|be responsible|responsible|resposible|in charge of|manage|provide|build|develop|work with|deal with|set up|represent|"
            r"prepare|submit|implementation|compliance|changes|complete|identify|title|gender|phase|clinical project|regional clinical trial|"
            r"rapidly analyse|explain|distinguish|establish a consulting group|interim monitoring visit|"
            r"target hospitals?|target hospital|china,\s*covering|covering more than|"
            r"curriculum vitae|employment history|clinical trial experience|therapeutic area expertise|project type|"
            r"summary of experience|dedicated project assistant)\b|"
            r"\b(?:working|yrs|training|reactivate|consumables|responsibilities|sales/r&d|including|application|business/kpi|"
            r"microsoft office|powerpoint|excel|solid communication skills|academic background|partnering with|phase iii|"
            r"regional clinical trial|global regional clinical trial|clinical stage global biotech company|according to company|"
            r"target patient group|customers maintenance|ability improvement|therapeutic area data|r\.d\. community|"
            r"medical advisor|mkt strategy|brand life-cycle management|product life-cycle management|kol|hcps?)\b|"
            r"\b(?:hospital|hospitals)\b.*\b(?:sales|strategy|channel|listing|performance|maximi[sz]e|minimi[sz]e|establish|access|target|achievement|coverage|standardize|standardized)\b|"
            r"\b(?:sales|strategy|channel|listing|performance|maximi[sz]e|minimi[sz]e|establish|access|target|achievement|coverage|standardize|standardized)\b.*\b(?:hospital|hospitals)\b|"
            r"\b(?:company|pharmaceutical ltd|pharmaceutical co)\b.*\b(?:headquarter|sales|products?|department|reporting|responsible|resposible)\b|"
            r"\binc$",
            value,
            re.IGNORECASE,
        )
    )


def _get_company_group(groups: list[dict[str, Any]], by_company: dict[str, dict[str, Any]], company: str) -> dict[str, Any]:
    group = by_company.get(company)
    if group is None:
        group = {"company": company, "roles": []}
        by_company[company] = group
        groups.append(group)
    return group


def _is_generic_company(company: str) -> bool:
    normalized = re.sub(r"[\s:_\-]+", "", str(company or "")).lower()
    return normalized in {
        "\u5de5\u4f5c\u7ecf\u5386",
        "workexperience",
        "professionalexperiences",
        "professionalexperience",
        "employmenthistory",
        "clinicaltrialexperience",
        "therapeuticareaexpertise",
        "curriculumvitae",
        "projecttype",
        "promotionhistory",
        "summary",
        "ltd.",
        "ltd",
        "co.",
        "co",
        "inc.",
        "inc",
        "-",
        "\u8d1f\u8d23\u516c\u53f8",
    }


def _is_placeholder_role(role: dict[str, Any]) -> bool:
    period = str(role.get("period") or "").strip()
    title = str(role.get("title") or "").strip()
    details = [str(item).strip() for item in role.get("details", []) if str(item).strip()]
    if period not in {"", "-"}:
        return False
    if _is_generic_company(title) and not details:
        return True
    return not title and bool(details) and all(_is_generic_company(item) for item in details)


def _is_profile_field(text: str) -> bool:
    return bool(PROFILE_FIELD_RE.match(str(text or "").strip()))


def _looks_like_education_line(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "").strip(" -|\uff1a:"))
    if not value:
        return False
    if re.search(r"\u5927\u5b66|\u5b66\u9662|\u4e2d\u5b66|\u5b66\u6821|\u6bd5\u4e1a\u9662\u6821|\u5b66\u5386|\u5b66\u4f4d|\u4e13\u4e1a|\u6559\u80b2\u7ecf\u5386|\u751f\u7269\u5de5\u7a0b", value):
        return True
    return bool(re.search(r"\b(?:university|college|school|education|degree|bachelor|master|major)\b", value, re.IGNORECASE))


def _looks_like_personal_value_line(text: str) -> bool:
    value = str(text or "").strip()
    if _is_profile_field(value):
        return True
    if re.fullmatch(r"[:\uff1a]?\s*1[3-9]\d{9}", value):
        return True
    if re.fullmatch(r"[:\uff1a]?\s*[\w.+-]+@[\w.-]+\.\w+", value):
        return True
    if re.fullmatch(r"[:\uff1a]?\s*(?:19|20)\d{2}[.\-/]\d{1,2}", value):
        return True
    return False


def _looks_like_personal_contamination_line(text: str) -> bool:
    value = str(text or "").strip()
    if _looks_like_personal_value_line(value):
        return True
    if re.search(r"现居地|手机|电话|邮箱", value):
        return True
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", value):
        return True
    return False


def _ordered_resume_text(blocks: dict[str, Any], original_resume: str) -> str:
    ordered: list[str] = []
    if blocks["personal"]:
        ordered.append("\u4e2a\u4eba\u4fe1\u606f")
        ordered.extend(f"{label}\uff1a{value}" for label, value in blocks["personal"])
        ordered.append("")
    if blocks["summary"]:
        ordered.append("\u81ea\u6211\u8bc4\u4ef7")
        ordered.extend(blocks["summary"])
        ordered.append("")
    if blocks["experience_groups"]:
        ordered.append("\u5de5\u4f5c\u7ecf\u5386")
        for group in blocks["experience_groups"]:
            ordered.append(str(group["company"]))
            for role in group["roles"]:
                ordered.append(str(role["period"]))
                if role.get("title"):
                    ordered.append(str(role["title"]))
                ordered.extend(str(item) for item in role.get("details", []))
                ordered.append("")
    if blocks.get("projects"):
        ordered.append("\u9879\u76ee\u7ecf\u5386")
        ordered.extend(str(item) for item in blocks["projects"])
        ordered.append("")
    if blocks["education"]:
        ordered.append("\u6559\u80b2\u7ecf\u5386")
        ordered.extend(blocks["education"])
        ordered.append("")
    if blocks["skills"]:
        ordered.append("\u6838\u5fc3\u6280\u80fd")
        ordered.extend(blocks["skills"])
        ordered.append("")
    value = "\n".join(ordered).strip()
    return value or blocks["fallback"] or original_resume


def _clean_items(items: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = _dedupe_text(str(item).strip())
        if not value:
            continue
        key = re.sub(r"\s+", "", value).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _dedupe_text(text: str) -> str:
    value = _strip_bullet_marker(str(text or ""))
    value = re.sub(r"\s+", " ", value).strip()
    value = _strip_profile_contamination(value)
    if not value:
        return ""
    parts = [part.strip() for part in re.split(r"(?<=[\u3002\uff01\uff1f\uff1b;])\s*", value) if part.strip()]
    if not parts:
        return value
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = re.sub(r"\s+", "", part).lower()
        if key and key not in seen:
            seen.add(key)
            result.append(part)
    return " ".join(result)


def _strip_profile_contamination(text: str) -> str:
    value = str(text or "")
    spaced_label = (
        r"\u59d3\s*\u540d|\u6c11\s*\u65cf|\u7535\s*\u8bdd|\u624b\s*\u673a|\u90ae\s*\u7bb1|"
        r"\u51fa\s*\u751f\s*\u5e74\s*\u6708|\u6bd5\s*\u4e1a\s*\u9662\s*\u6821|\u5b66\s*\u5386|\u4f4f\s*\u5740"
    )
    value = re.split(
        rf"(?:\u5de5\u4f5c\u7ecf\u5386)+\s*(?={spaced_label})|"
        rf"(?=\s*(?:{spaced_label})\s*[:\uff1a])",
        value,
        maxsplit=1,
    )[0]
    return value.strip()


def _strip_bullet_marker(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^[\u2022\u25cf\u25e6\u2219\u26ab\u00b7\-]+\s*", "", value)
    return "" if re.fullmatch(r"[\u2022\u25cf\u25e6\u2219\u26ab\u00b7\-]+", value) else value


def _extract_period(text: str) -> str:
    english_to = ENGLISH_TO_PERIOD_RE.search(text)
    if english_to:
        return english_to.group(0).strip()
    month_match = MONTH_PERIOD_RE.search(text)
    if month_match:
        return month_match.group(0).strip()
    flex_match = FLEX_PERIOD_RE.search(text)
    if flex_match:
        return flex_match.group(0).strip()
    match = PERIOD_RE.search(text)
    if match:
        return match.group(0).strip()
    partial = PARTIAL_CURRENT_PERIOD_RE.search(text)
    return partial.group(0).strip() if partial else ""


def _extract_pdf_split_year_title(text: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*((?:19|20)\d{2})[.\u3002]?\s+(.{2,36})\s*$", str(text or "").strip())
    if not match:
        return None
    title = match.group(2).strip(" -|\uff1a:")
    if not _looks_like_role_title(title):
        return None
    return match.group(1), title


def _is_partial_current_period(period: str) -> bool:
    return bool(PARTIAL_CURRENT_PERIOD_RE.fullmatch(str(period or "").strip())) and not re.match(r"^(?:19|20)\d{2}", str(period or "").strip())


def _complete_partial_current_period(period: str, year: str) -> str:
    value = re.sub(r"\s+", "", str(period or "").strip())
    return f"{year}.{value}"


def _is_pdf_split_noise_title(title: str) -> bool:
    return str(title or "").strip() in {"\u83b7\u5f97", "\u804c\u8d23", "\u4e3b\u8981\u804c\u8d23"}


def _extract_company(text: str) -> str:
    match = re.search(
        r"([\u4e00-\u9fffA-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff0-9\uff08\uff09()&.,'’路\-\s]{2,}?"
        r"(?:\u6709\u9650\u516c\u53f8|\u96c6\u56e2|\u533b\u9662|\u4e2d\u5fc3|\u516c\u53f8|"
        r"Company|Group|Ltd\.?|Inc\.?|GmbH|KG|ApS|Rep\.?\s*Office))",
        text,
        re.IGNORECASE,
    )
    if not match:
        return ""
    company = _strip_english_role_prefix_from_company(re.sub(r"\s+", " ", match.group(1)).strip())
    tail = re.sub(r"\s+", " ", str(text or "")[match.end():]).strip(" -|\uff1a:")
    if tail and not _looks_like_english_role_title(tail) and not _looks_like_english_resume_fragment(tail):
        if re.search(r"\b(?:&\s*Co\.?\s*KG|Shanghai|China|Rep\.?\s*Office|Office)\b", tail, re.IGNORECASE):
            company = f"{company} {tail}".strip()
    if _looks_like_english_resume_fragment(company):
        return ""
    if _looks_like_business_object_not_company(company):
        return ""
    return "" if _is_generic_company(company) else company


def _extract_service_company(text: str) -> str:
    match = re.match(r"^\s*\u670d\u52a1\u516c\u53f8\s*[:\uff1a]\s*(.+?)\s*$", str(text or ""))
    if not match:
        return ""
    value = match.group(1).strip(" -|\uff1a:")
    return value if value and not _looks_like_personal_value_line(value) else ""


def _extract_service_role(text: str) -> str:
    match = re.match(r"^\s*\u90e8\u95e8\u804c\u52a1\s*[:\uff1a]\s*(.+?)\s*$", str(text or ""))
    if not match:
        return ""
    value = match.group(1).strip(" -|\uff1a:")
    return value if value and not _looks_like_personal_value_line(value) else ""


def _strip_english_role_prefix_from_company(company: str) -> str:
    value = re.sub(r"\s+", " ", str(company or "").strip(" -|\uff1a:"))
    value = re.sub(r"^(?:I{1,3}|IV|V)\.\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^Work in\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(
        r"^(?:Product|Brand|Marketing|Sales|Project|Clinical|Senior|Associate)?\s*"
        r"(?:Manager|Director|Representative|Assistant|Associate)\s+of\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    if not value or re.search(r"[\u4e00-\u9fff]", value):
        return value
    parts = [part.strip(" -|\uff1a:") for part in value.split(",") if part.strip(" -|\uff1a:")]
    if len(parts) <= 1:
        return value
    best = ""
    for index, part in enumerate(parts):
        candidate = ", ".join(parts[index:]).strip()
        if not re.search(r"\b(?:Company|Group|Ltd\.?|Inc\.?|GmbH|KG|ApS|Co\.?)\b", candidate, re.IGNORECASE):
            continue
        words = re.findall(r"[A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff]+", candidate)
        if len(words) < 2 or re.fullmatch(r"(?:co|ltd|inc|kg|aps|gmbh)\.?", candidate, re.IGNORECASE):
            continue
        best = candidate
    return best or value


def _looks_like_detail(text: str) -> bool:
    return bool(
        re.search(
            r"\u8d1f\u8d23|\u8fbe\u6210|\u589e\u957f|\u4fdd\u7559|\u63a8\u5e7f|\u51c6\u5165|"
            r"\u56e2\u961f|\u5ba2\u6237|\u5e02\u573a|\u4ea7\u54c1|\u533b\u9662|\d+%",
            text,
        )
    )


def _salary_summary(data: dict[str, Any]) -> str:
    explicit = str(data.get("salary_info") or "").strip()
    if explicit:
        return explicit
    parts = []
    current = str(data.get("current_salary") or "").strip()
    expected = str(data.get("expected_salary") or "").strip()
    if current:
        parts.append(f"\u5f53\u524d\u85aa\u8d44\uff1a{current}")
    if expected:
        parts.append(f"\u671f\u671b\u85aa\u8d44\uff1a{expected}")
    return "\uff1b".join(parts)


def _detect_report_language(data: dict[str, Any], original_resume: str) -> str:
    explicit = str(data.get("report_language") or "").strip().lower()
    if explicit in {"zh", "cn", "chinese"}:
        return "zh"
    if explicit in {"en", "english"}:
        return "en"
    probe = " ".join(
        str(item or "")
        for item in [
            data.get("candidate_name"),
            data.get("position_title"),
            data.get("job_description"),
            original_resume,
        ]
    )
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", probe))
    latin_words = len(re.findall(r"\b[A-Za-z]{3,}\b", probe))
    return "zh" if chinese_chars >= max(3, latin_words // 2) else "en"


def _localized_text(text: str, language: str) -> str:
    value = str(text or "").strip()
    if not value or value == "-":
        return value or "-"
    if language == "zh":
        cn_parts = re.findall(r"CN:\s*(.*?)(?=\s+EN:|$)", value, flags=re.IGNORECASE | re.DOTALL)
        if cn_parts:
            return _clean_language_prefix(" ".join(part.strip() for part in cn_parts if part.strip()))
        value = re.sub(r"EN:\s*.*?(?=\s+CN:|$)", "", value, flags=re.IGNORECASE | re.DOTALL).strip()
        return _clean_language_prefix(value)

    en_parts = re.findall(r"EN:\s*(.*?)(?=\s+CN:|$)", value, flags=re.IGNORECASE | re.DOTALL)
    if en_parts:
        return _clean_language_prefix(" ".join(part.strip() for part in en_parts if part.strip()))
    value = re.sub(r"CN:\s*.*?(?=\s+EN:|$)", "", value, flags=re.IGNORECASE | re.DOTALL).strip()
    return _clean_language_prefix(value)


def _clean_language_prefix(text: str) -> str:
    value = re.sub(r"\b(?:EN|CN)\s*:\s*", "", str(text or ""), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip() or "-"


def _report_style(data: dict[str, Any]) -> str:
    value = str(data.get("report_style") or "tstar_warm").strip()
    return value if value in {"tstar_warm", "consulting_blue"} else "tstar_warm"


def _value(data: dict[str, Any], key: str, fallback: str = "-") -> str:
    value = data.get(key)
    return fallback if value is None or value == "" else str(value)


def _compact_join(values: list[Any]) -> str:
    return " / ".join(str(value) for value in values if value)


__all__ = ["build_placeholder_context"]

