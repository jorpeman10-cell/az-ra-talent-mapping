from __future__ import annotations

import re
from typing import Any


SECTION_ALIASES = {
    "\u4e2a\u4eba\u7b80\u5386": "document_title",
    "personal resume": "document_title",
    "resume": "document_title",
    "\u4e2a\u4eba\u4fe1\u606f": "personal",
    "\u57fa\u672c\u4fe1\u606f": "personal",
    "personal information": "personal",
    "\u6c42\u804c\u610f\u5411": "intention",
    "\u610f\u5411\u5c97\u4f4d": "intention",
    "career objective": "intention",
    "\u81ea\u6211\u8bc4\u4ef7": "summary",
    "\u4e2a\u4eba\u6982\u8ff0": "summary",
    "self-evaluation": "summary",
    "self evaluation": "summary",
    "profile": "summary",
    "summary": "summary",
    "summary of experience": "summary",
    "therapeutic area expertise": "skills",
    "\u5de5\u4f5c\u7ecf\u5386": "experience",
    "\u5de5\u4f5c\u7ecf\u9a8c": "experience",
    "employment history": "experience",
    "employment experience": "experience",
    "employment experiences": "experience",
    "career history": "experience",
    "working experience": "experience",
    "promotion history": "experience",
    "professional experience": "experience",
    "professional experiences": "experience",
    "work experience": "experience",
    "experience": "experience",
    "\u9879\u76ee\u7ecf\u5386": "projects",
    "\u9879\u76ee\u7ecf\u9a8c": "projects",
    "\u53c2\u4e0e\u9879\u76ee": "projects",
    "\u79d1\u7814\u7ecf\u5386": "projects",
    "\u5b66\u4e60\u53ca\u79d1\u7814\u7ecf\u5386": "projects",
    "\u5b66\u4e60\u4e0e\u79d1\u7814\u7ecf\u5386": "projects",
    "\u7814\u7a76\u7ecf\u5386": "projects",
    "\u6821\u56ed\u7ecf\u5386": "projects",
    "\u5b9e\u4e60\u7ecf\u5386": "projects",
    "clinical trial experience": "projects",
    "campus experience": "projects",
    "internship experience": "projects",
    "project experience": "projects",
    "\u6838\u5fc3\u6280\u80fd": "skills",
    "\u76f8\u5173\u6280\u80fd": "skills",
    "\u4e13\u4e1a\u6280\u80fd": "skills",
    "professional skills": "skills",
    "core skills": "skills",
    "skills": "skills",
    "\u6559\u80b2\u7ecf\u5386": "education",
    "\u6559\u80b2\u80cc\u666f": "education",
    "education": "education",
    "\u8363\u8a89": "certificates",
    "\u8363\u8a89\u8bc1\u4e66": "certificates",
    "\u8bc1\u4e66": "certificates",
    "certificates": "certificates",
}

SECTION_TITLES = {
    "personal": "Personal Information / \u4e2a\u4eba\u4fe1\u606f",
    "intention": "Career Intention / \u6c42\u804c\u610f\u5411",
    "summary": "Profile / \u81ea\u6211\u8bc4\u4ef7",
    "experience": "Work Experience / \u5de5\u4f5c\u7ecf\u5386",
    "projects": "Project Experience / \u9879\u76ee\u7ecf\u5386",
    "skills": "Skills / \u6838\u5fc3\u6280\u80fd",
    "education": "Education / \u6559\u80b2\u7ecf\u5386",
    "certificates": "Certificates / \u8363\u8a89\u8bc1\u4e66",
    "unclassified": "Parsed Resume / \u7b80\u5386\u539f\u6587",
}

SECTION_LABEL_PATTERN = (
    r"\u4e2a\u4eba\u4fe1\u606f|\u57fa\u672c\u4fe1\u606f|\u81ea\u6211\u8bc4\u4ef7|"
    r"\u5de5\u4f5c\u7ecf\u5386|\u5de5\u4f5c\u7ecf\u9a8c|\u9879\u76ee\u7ecf\u5386|\u9879\u76ee\u7ecf\u9a8c|"
    r"\u53c2\u4e0e\u9879\u76ee|\u79d1\u7814\u7ecf\u5386|\u5b66\u4e60\u53ca\u79d1\u7814\u7ecf\u5386|"
    r"\u5b66\u4e60\u4e0e\u79d1\u7814\u7ecf\u5386|\u7814\u7a76\u7ecf\u5386|\u6821\u56ed\u7ecf\u5386|\u5b9e\u4e60\u7ecf\u5386|"
    r"\u6559\u80b2\u7ecf\u5386|\u8363\u8a89\u8bc1\u4e66|\u8363\u8a89|\u8bc1\u4e66|"
    r"\u6559\u80b2\u80cc\u666f|\u6c42\u804c\u610f\u5411|\u610f\u5411\u5c97\u4f4d|"
    r"\u6838\u5fc3\u6280\u80fd|\u76f8\u5173\u6280\u80fd|\u4e13\u4e1a\u6280\u80fd|"
        r"self[- ]?evaluation|summary of experience|therapeutic area expertise|"
        r"employment history|employment experiences?|career history|working experience|promotion history|"
        r"clinical trial experience|campus experience|internship experience|professional experiences?|work experience|"
        r"project experience|professional skills|core skills|certificates?"
)

FIELD_LABEL_PATTERN = (
    r"\u59d3\u540d|\u6c11\u65cf|\u7535\u8bdd|\u624b\u673a|\u90ae\u7bb1|"
    r"\u7535\u5b50\u90ae\u7bb1|\u51fa\u751f\u5e74\u6708|\u6bd5\u4e1a\u9662\u6821|"
    r"\u5b66\u5386|\u5b66\u4f4d|\u4e13\u4e1a|\u4f4f\u5740|\u5730\u5740|"
    r"\u73b0\u6240\u5728\u5730|\u653f\u6cbb\u9762\u8c8c|\u671f\u671b\u85aa\u8d44|"
    r"\u670d\u52a1\u516c\u53f8|\u90e8\u95e8\u804c\u52a1|"
    r"\u81ea\u6211\u8bc4\u4ef7|\u5de5\u4f5c\u7ecf\u5386|\u6559\u80b2\u7ecf\u5386|"
    r"\u6c42\u804c\u610f\u5411|\u610f\u5411\u5c97\u4f4d"
)

PERIOD_RE = re.compile(
    r"(?:19|20)\d{2}(?:[.\-/\u5e74]\d{1,2}\u6708?)?\s*[-~\u2013\u2014\u81f3]+"
    r"\s*(?:\u81f3\u4eca|\u73b0\u5728|present|current|(?:19|20)\d{2}(?:[.\-/\u5e74]\d{1,2}\u6708?)?)",
    re.IGNORECASE,
)
ENGLISH_TO_PERIOD_RE = re.compile(
    r"(?:(?:\d{1,2}\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+)?"
    r"(?:19|20)\d{2}\s+to\s+"
    r"(?:(?:\d{1,2}\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+)?"
    r"(?:present|current|(?:19|20)\d{2})",
    re.IGNORECASE,
)
PARTIAL_CURRENT_PERIOD_RE = re.compile(
    r"\d{1,2}\s*\u6708\s*[-~\u2013\u2014\u81f3]+\s*(?:\u81f3\u4eca|\u73b0\u5728|present|current)",
    re.IGNORECASE,
)
COMPANY_SIGNAL_RE = re.compile(
    r"(\u6709\u9650\u516c\u53f8|\u516c\u53f8|\u96c6\u56e2|\u533b\u9662|\u4e2d\u5fc3|pharma|medical|inc\.|ltd\.|co\.)",
    re.IGNORECASE,
)
ROLE_OR_ACHIEVEMENT_RE = re.compile(
    r"(\u7ecf\u7406|\u4ee3\u8868|\u4e3b\u4efb|\u603b\u76d1|\u8d1f\u8d23|\u4efb\u804c|\u7ba1\u7406|"
    r"\u63a8\u5e7f|\u51c6\u5165|\u8fbe\u6210|\u589e\u957f|\u56e2\u961f|\u4ea7\u54c1|\u533b\u9662|"
    r"\u5ba2\u6237|\u533a\u57df|\u9500\u552e|manager|director|\bmr\b|s,?\s*mr|led|managed|achieved|"
    r"sales|market|training|team|kam|business|distribution|\d+\s*%)",
    re.IGNORECASE,
)
BULLET_MARKER_RE = re.compile(r"^[\u2022\u25cf\u25e6\u2219\u26ab\u00b7\-]+\s*")


def parse_resume_for_report(text: str) -> dict[str, Any]:
    normalized = _normalize(text)
    lines = _meaningful_lines(normalized)
    sections = _refine_sections(_extract_sections(normalized), lines)
    evidence = _evidence_lines(lines)
    structured = _structured_sections(lines, evidence, sections)
    quality = assess_resume_text_quality(normalized, lines, sections)
    return {
        "text": normalized,
        "lines": lines,
        "evidence": evidence,
        "structured": structured,
        "quality": quality,
        "line_count": len(lines),
        "char_count": len(normalized),
    }


def assess_resume_text_quality(
    text: str,
    lines: list[str] | None = None,
    sections: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    value = _normalize(text)
    line_items = lines if lines is not None else _meaningful_lines(value)
    section_items = sections if sections is not None else _refine_sections(_extract_sections(value), line_items)
    char_count = len(value)
    non_space_count = len(re.sub(r"\s+", "", value))
    has_contact = bool(re.search(r"[\w.+-]+@[\w.-]+\.\w+|(?:\+?86[-\s]?)?1[3-9]\d{9}", value))
    has_work_signal = bool(
        section_items.get("experience")
        or section_items.get("projects")
        or PERIOD_RE.search(value)
        or ENGLISH_TO_PERIOD_RE.search(value)
        or COMPANY_SIGNAL_RE.search(value.lower())
    )
    reasons: list[str] = []
    needs_ocr = False
    if char_count == 0:
        reasons.append("empty_text")
        needs_ocr = True
    elif non_space_count < 120:
        reasons.append("very_short_text")
        needs_ocr = not has_work_signal
    elif char_count < 350 and not has_work_signal:
        reasons.append("short_text_without_work_signal")
    if line_items and len(line_items) < 6 and char_count < 600:
        reasons.append("too_few_lines")
    if not has_work_signal:
        reasons.append("missing_work_or_project_signal")
    if char_count >= 350 and not has_contact:
        reasons.append("missing_contact_signal")

    if not reasons:
        status = "ok"
    elif needs_ocr:
        status = "needs_ocr"
    else:
        status = "low_confidence"
    return {
        "status": status,
        "reasons": reasons,
        "char_count": char_count,
        "line_count": len(line_items),
        "has_contact_signal": has_contact,
        "has_work_signal": has_work_signal,
        "needs_ocr": needs_ocr,
    }


def resume_text_from_data(data: dict[str, Any]) -> str:
    parsed = data.get("parsed_resume")
    if isinstance(parsed, dict) and parsed.get("text"):
        return str(parsed["text"])
    return str(data.get("original_resume") or data.get("resume_text") or "").strip()


def resume_evidence_from_data(data: dict[str, Any], limit: int = 8) -> list[str]:
    parsed = data.get("parsed_resume")
    if isinstance(parsed, dict) and isinstance(parsed.get("evidence"), list):
        evidence = [str(item).strip() for item in parsed["evidence"] if str(item).strip()]
        if evidence:
            return evidence[:limit]
    return _evidence_lines(_meaningful_lines(resume_text_from_data(data)))[:limit]


def resume_lines_from_data(data: dict[str, Any], limit: int | None = None) -> list[str]:
    parsed = data.get("parsed_resume")
    if isinstance(parsed, dict) and isinstance(parsed.get("lines"), list):
        lines = [str(item).strip() for item in parsed["lines"] if str(item).strip()]
    else:
        lines = _meaningful_lines(resume_text_from_data(data))
    return lines if limit is None else lines[:limit]


def resume_sections_from_data(data: dict[str, Any]) -> dict[str, list[str]]:
    parsed = data.get("parsed_resume")
    if isinstance(parsed, dict) and isinstance(parsed.get("structured"), dict):
        sections = parsed["structured"].get("sections")
        if isinstance(sections, dict):
            return {
                str(key): [str(item).strip() for item in value if str(item).strip()]
                for key, value in sections.items()
                if isinstance(value, list)
            }
    return _extract_sections(resume_text_from_data(data))


def resume_work_experience_from_data(data: dict[str, Any], limit: int = 8) -> list[str]:
    parsed = data.get("parsed_resume")
    if isinstance(parsed, dict):
        structured = parsed.get("structured")
        if isinstance(structured, dict) and isinstance(structured.get("experience_items"), list):
            items = [_clean_resume_line(str(item)) for item in structured["experience_items"] if str(item).strip()]
            if items:
                return _unique(items, limit)
    sections = resume_sections_from_data(data)
    return _unique([_clean_resume_line(item) for item in sections.get("experience", [])], limit)


def _normalize(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _meaningful_lines(text: str) -> list[str]:
    raw_lines: list[str] = []
    for block in text.splitlines():
        for item in _explode_resume_line(block):
            item = item.strip(" -\u2022\t|")
            if len(item) < 2:
                continue
            if _canonical_section(item) or len(item) <= 220:
                raw_lines.append(item)
                continue
            raw_lines.extend(
                part.strip(" -\u2022\t|")
                for part in _split_long_line(item)
                if len(part.strip(" -\u2022\t|")) >= 6
            )

    if not raw_lines and text:
        raw_lines = [text[i : i + 180].strip() for i in range(0, min(len(text), 5000), 180)]

    seen: set[str] = set()
    lines: list[str] = []
    for line in raw_lines:
        key = re.sub(r"\s+", " ", line)
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def _explode_resume_line(block: str) -> list[str]:
    value = str(block or "").strip()
    if not value:
        return []
    value = re.sub(r"\s*\|\s*", "\n", value)
    value = re.sub(rf"(?<!^)\s*({SECTION_LABEL_PATTERN})(?=\s|$)", r"\n\1\n", value)
    value = re.sub(rf"^({SECTION_LABEL_PATTERN})(?=\s+)", r"\1\n", value)
    value = re.sub(rf"(?<!^)\s*((?:{FIELD_LABEL_PATTERN})\s*[:\uff1a])", r"\n\1", value)
    value = re.sub(
        r"(?<!^)\s*((?:19|20)\d{2}[.\-/\u5e74]?\d{0,2}\u6708?\s*[-~\u2013\u2014\u81f3])",
        r"\n\1",
        value,
    )
    return [part.strip() for part in value.splitlines() if part.strip()]


def _split_long_line(line: str) -> list[str]:
    parts = re.split(r"(?<=[.!?\u3002\uff01\uff1f\uff1b;])\s+", line)
    if len(parts) <= 1:
        return [line[i : i + 180].strip() for i in range(0, len(line), 180)]
    return parts


def _extract_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "unclassified"
    for raw_line in text.splitlines():
        for item in _explode_resume_line(raw_line):
            line = item.strip(" \t\r\n-|")
            if not line:
                continue
            canonical = _canonical_section(line)
            if canonical:
                if canonical == "document_title":
                    continue
                current = canonical
                sections.setdefault(current, [])
                continue
            sections.setdefault(current, []).append(line)
    return {key: _unique(value, 240) for key, value in sections.items() if value}


def _refine_sections(sections: dict[str, list[str]], lines: list[str]) -> dict[str, list[str]]:
    refined: dict[str, list[str]] = {key: [] for key in SECTION_TITLES if key != "unclassified"}
    active = ""

    candidates: list[tuple[str, str]] = []
    for key, values in sections.items():
        for value in values:
            candidates.append((key, value))
    if not candidates:
        candidates = [("", line) for line in lines]

    for original_key, raw in candidates:
        line = _clean_resume_line(raw)
        if not line or _is_noise_line(line):
            continue
        canonical = _canonical_section(line)
        if canonical:
            active = "" if canonical == "document_title" else canonical
            continue
        key = _classify_resume_line(line, original_key, active)
        if key:
            refined.setdefault(key, []).append(line)
            if not (original_key == "experience" and key in {"personal", "education", "intention"}):
                active = key if key != "personal" else active

    return {key: _unique(value, 240) for key, value in refined.items() if value}


def _clean_resume_line(line: str) -> str:
    value = re.sub(r"\s+", " ", str(line or "")).strip(" -\u2022\u25cf\u26ab\t|")
    value = BULLET_MARKER_RE.sub("", value).strip()
    value = re.sub(r"^\u59d3\s+\u540d\s*[:\uff1a]\s*", "\u59d3\u540d\uff1a", value)
    value = re.sub(r"^\u7535\s+\u8bdd\s*[:\uff1a]\s*", "\u7535\u8bdd\uff1a", value)
    value = re.sub(r"^\u90ae\s+\u7bb1\s*[:\uff1a]\s*", "\u90ae\u7bb1\uff1a", value)
    value = re.sub(r"^\u6c11\s+\u65cf\s*[:\uff1a]\s*", "\u6c11\u65cf\uff1a", value)
    value = re.sub(r"^\u5b66\s+\u5386\s*[:\uff1a]\s*", "\u5b66\u5386\uff1a", value)
    value = re.sub(r"^\u4f4f\s+\u5740\s*[:\uff1a]\s*", "\u4f4f\u5740\uff1a", value)
    return value


def _is_noise_line(line: str) -> bool:
    normalized = re.sub(r"[\s:\uff1a|_\-，,。.!！?？；;]+", "", line).lower()
    if "\u7ec6\u5fc3\u4ece\u6bcf\u4e00\u4e2a\u5c0f\u7ec6\u8282\u5f00\u59cb" in normalized:
        return True
    return normalized in {
        "\u4e2a\u4eba\u7b80\u5386",
        "personalresume",
        "resume",
        "\u57fa\u672c\u4fe1\u606f",
        "\u7ec6\u5fc3\u4ece\u6bcf\u4e00\u4e2a\u5c0f\u7ec6\u8282\u5f00\u59cb",
    }


def _classify_resume_line(line: str, original_key: str, active: str) -> str:
    lower = line.lower()
    if re.match(r"^(?:\u81ea\u6211\u8bc4\u4ef7|\u4e2a\u4eba\u6982\u8ff0)", line):
        return "summary"
    if re.search(
        rf"^(?:{FIELD_LABEL_PATTERN})\s*[:\uff1a]",
        line,
    ):
        if re.search(r"^(?:\u6bd5\u4e1a\u9662\u6821|\u5b66\u5386|\u5b66\u4f4d|\u4e13\u4e1a)\s*[:\uff1a]", line):
            return "education"
        if re.search(r"^(?:\u610f\u5411\u5c97\u4f4d|\u6c42\u804c\u610f\u5411|\u671f\u671b\u85aa\u8d44)\s*[:\uff1a]", line):
            return "intention"
        if re.search(r"^(?:\u670d\u52a1\u516c\u53f8|\u90e8\u95e8\u804c\u52a1)\s*[:\uff1a]", line):
            return "experience"
        if re.search(r"^(?:\u81ea\u6211\u8bc4\u4ef7|\u4e2a\u4eba\u6982\u8ff0)\s*[:\uff1a]?", line):
            return "summary"
        return "personal"
    if original_key in {"projects", "certificates"}:
        return original_key
    if _has_explicit_experience_signal(line, lower):
        return "experience"
    if original_key in {"personal", "intention", "summary", "projects", "skills", "education", "certificates"}:
        return original_key
    if PERIOD_RE.search(line) or PARTIAL_CURRENT_PERIOD_RE.search(line) or re.search(r"\u81f3\u4eca|present|current", lower):
        return "experience"
    if COMPANY_SIGNAL_RE.search(lower) and not re.search(r"\u90ae\u7bb1|\u7535\u8bdd|\u5730\u5740|\u4f4f\u5740", line):
        return "experience"
    if ROLE_OR_ACHIEVEMENT_RE.search(lower):
        return "experience"
    if original_key == "experience":
        return original_key
    if active:
        return active
    return ""


def _has_explicit_experience_signal(line: str, lower: str) -> bool:
    if re.search(r"\u90ae\u7bb1|\u7535\u8bdd|\u624b\u673a|\u5730\u5740|\u4f4f\u5740", line) and not COMPANY_SIGNAL_RE.search(lower):
        return False
    has_period = bool(
        PERIOD_RE.search(line)
        or ENGLISH_TO_PERIOD_RE.search(line)
        or PARTIAL_CURRENT_PERIOD_RE.search(line)
        or re.search(r"\u81f3\u4eca|present|current", lower)
    )
    has_company = bool(COMPANY_SIGNAL_RE.search(lower))
    has_role_or_achievement = bool(ROLE_OR_ACHIEVEMENT_RE.search(lower))
    return (has_period and (has_company or has_role_or_achievement)) or (has_company and has_role_or_achievement)


def _canonical_section(line: str) -> str:
    normalized = re.sub(r"[\s:\uff1a|/\\\-_\u3000]+", "", line.strip()).lower()
    for label, canonical in SECTION_ALIASES.items():
        if normalized == re.sub(r"[\s:\uff1a|/\\\-_\u3000]+", "", label).lower():
            return canonical
    return ""


def _evidence_lines(lines: list[str]) -> list[str]:
    keywords = [
        "launch",
        "oncology",
        "medical",
        "sales",
        "strategy",
        "kol",
        "\u533b\u836f",
        "\u533b\u5b66",
        "\u589e\u957f",
        "\u8fbe\u6210",
        "\u8d1f\u8d23",
        "\u7ba1\u7406",
        "\u56e2\u961f",
        "\u4ea7\u54c1",
        "\u533b\u9662",
        "\u51c6\u5165",
        "\u63a8\u5e7f",
    ]
    scored: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        lower = line.lower()
        score = sum(2 for keyword in keywords if keyword in lower)
        if re.search(r"\d+\s*%|\d+\s*\u5e74|top|no\.", lower):
            score += 3
        if score > 0:
            scored.append((score, -index, line))
    scored.sort(reverse=True)
    selected = [line for _, _, line in scored]
    if len(selected) < 4:
        selected.extend(line for line in lines if line not in selected)
    return selected[:10]


def _structured_sections(lines: list[str], evidence: list[str], sections: dict[str, list[str]]) -> dict[str, Any]:
    experience_items: list[str] = []
    achievement_items: list[str] = []
    keyword_items: list[str] = []
    risk_items: list[str] = []

    if sections.get("experience"):
        experience_items.extend(_join_resume_blocks(sections["experience"]))
    if sections.get("summary"):
        keyword_items.extend(sections["summary"])
    if sections.get("skills"):
        keyword_items.extend(sections["skills"])

    for line in lines:
        lower = line.lower()
        if _looks_like_experience(line, lower):
            experience_items.append(line)
        if _looks_like_achievement(line, lower):
            achievement_items.append(line)
        if _looks_like_keyword_evidence(lower):
            keyword_items.append(line)
        if _looks_like_risk_gap(lower):
            risk_items.append(line)

    if not experience_items:
        experience_items = lines[:5]
    if not achievement_items:
        achievement_items = evidence[:5]
    if not keyword_items:
        keyword_items = evidence[:5]

    return {
        "experience_items": _unique(experience_items, 16),
        "achievement_items": _unique(achievement_items, 8),
        "keyword_items": _unique(keyword_items, 10),
        "risk_items": _unique(risk_items, 6),
        "sections": sections,
        "section_titles": SECTION_TITLES,
    }


def _join_resume_blocks(lines: list[str]) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if current and PERIOD_RE.search(line):
            blocks.append(" ".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(" ".join(current).strip())
    return blocks


def _looks_like_experience(line: str, lower: str) -> bool:
    return bool(
        PERIOD_RE.search(line)
        or ENGLISH_TO_PERIOD_RE.search(line)
        or re.search(
            r"present|current|\u81f3\u4eca|\u5de5\u4f5c|\u8d1f\u8d23|\u4efb\u804c|managed|led|director|manager|head",
            lower,
        )
        or (len(line) > 60 and _looks_like_keyword_evidence(lower))
    )


def _looks_like_achievement(line: str, lower: str) -> bool:
    return bool(
        re.search(
            r"\d+\s*%|\d+\s*(x|\u500d|\u5e74|\u4eba|\u5bb6|\u4e2a|\u4ebf|\u4e07)|top|no\.|"
            r"achieved|built|launched|growth|\u589e\u957f|\u8fbe\u6210|\u63d0\u5347|\u7b2c\u4e00",
            lower,
        )
    )


def _looks_like_keyword_evidence(lower: str) -> bool:
    keywords = [
        "oncology",
        "medical",
        "strategy",
        "launch",
        "kol",
        "market access",
        "sales",
        "team",
        "\u533b\u5b66",
        "\u533b\u836f",
        "\u80bf\u7624",
        "\u7b56\u7565",
        "\u4e0a\u5e02",
        "\u51c6\u5165",
        "\u56e2\u961f",
        "\u533b\u9662",
        "\u4ea7\u54c1",
    ]
    return any(keyword in lower for keyword in keywords)


def _looks_like_risk_gap(lower: str) -> bool:
    keywords = ["gap", "pending", "unknown", "\u79bb\u804c", "\u7a7a\u7a97", "\u5f85\u786e\u8ba4", "\u98ce\u9669", "\u4e0d\u660e\u786e"]
    return any(keyword in lower for keyword in keywords)


def _unique(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = re.sub(r"\s+", " ", str(item)).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(str(item))
        if len(result) >= limit:
            break
    return result


__all__ = [
    "assess_resume_text_quality",
    "parse_resume_for_report",
    "resume_evidence_from_data",
    "resume_lines_from_data",
    "resume_sections_from_data",
    "resume_text_from_data",
    "resume_work_experience_from_data",
]
