from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.parser import extract_uploaded_text
from core.placeholder_report import build_placeholder_context
from core.resume_parser import parse_resume_for_report


DEFAULT_HOST = "139.129.192.85"
DEFAULT_PORT = 9998
DEFAULT_USER = "root"
DEFAULT_KEY = Path.home() / ".ssh" / "Hiijob.pem"


REMOTE_COLLECTOR = r"""
import base64
import datetime as dt
import json
import os
from collections import defaultdict

import pymysql

LIMIT = int(__LIMIT__)
OVERFETCH = int(__OVERFETCH__)
MAX_BYTES = int(__MAX_BYTES__)
SAMPLE_MODE = "__SAMPLE_MODE__"
GLLUE_CONFIG = "/root/hiijob-federation/gllue-config.json"
HUNTER_DB_CONFIG = "/root/hunter-server/db_config.properties"
JUNK_NAME_PATTERNS = ["粘贴简历", "旧简历", "截图", "图片", "微信图片"]
ALLOWED_EXTS = {"pdf", "docx", "txt", "md"}


def load_hunter_db_password():
    for line in open(HUNTER_DB_CONFIG, encoding="utf-8", errors="ignore").read().splitlines():
        s = line.strip()
        if s.startswith("database_password") and not s.startswith("#"):
            return s.partition("=")[2].strip()
    raise RuntimeError("database_password not found")


def gllue_connect():
    cfg = json.load(open(GLLUE_CONFIG, encoding="utf-8"))
    return pymysql.connect(
        host=cfg["host"],
        port=int(cfg.get("port", 3306)),
        user=cfg["username"],
        password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def hunter_connect():
    return pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password=load_hunter_db_password(),
        database="hunter",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def is_junk(name):
    return bool(name) and any(p in name for p in JUNK_NAME_PATTERNS)


def pick_best(rows):
    original = [r for r in rows if r.get("tag") == "Original CV" and not is_junk(r.get("originname"))]
    pool = original if original else [r for r in rows if not is_junk(r.get("originname"))]
    if not pool:
        pool = rows
    return max(pool, key=lambda r: r.get("dateAdded") or dt.datetime.min)


def resolve_path(row):
    if row.get("real_preview_path"):
        return row["real_preview_path"], "preview", "pdf"
    if row.get("originpath"):
        return row["originpath"], "origin", str(row.get("ext") or "").lower().lstrip(".")
    added = row.get("dateAdded")
    ym = added.strftime("%Y-%m") if hasattr(added, "strftime") else str(added)[:7]
    ext = str(row.get("ext") or "").lower().lstrip(".")
    return f"/opt/upload/candidate/{ym}/{row.get('uuidname')}.{ext}", "derived", ext


def main():
    hconn = hunter_connect()
    try:
        with hconn.cursor() as cur:
            if SAMPLE_MODE == "spread":
                cur.execute(
                    "SELECT COUNT(*) AS total FROM resume "
                    "WHERE resume_source_id REGEXP '^[0-9]+$' AND is_deleted=0"
                )
                total = int((cur.fetchone() or {}).get("total") or 0)
                target = min(total, max(LIMIT * 10, LIMIT + 100), 5000)
                offsets = []
                if target > 0:
                    if target == 1:
                        offsets = [0]
                    else:
                        offsets = [int(i * max(total - 1, 0) / max(target - 1, 1)) for i in range(target)]
                candidates = []
                for offset in offsets:
                    cur.execute(
                        "SELECT id, name, current_enterprise, current_position, resume_source_id, modified_time "
                        "FROM resume "
                        "WHERE resume_source_id REGEXP '^[0-9]+$' AND is_deleted=0 "
                        "ORDER BY modified_time DESC, id DESC LIMIT 1 OFFSET %s",
                        (offset,),
                    )
                    row = cur.fetchone()
                    if row:
                        candidates.append(row)
            else:
                cur.execute(
                    "SELECT id, name, current_enterprise, current_position, resume_source_id, modified_time "
                    "FROM resume "
                    "WHERE resume_source_id REGEXP '^[0-9]+$' AND is_deleted=0 "
                    "ORDER BY modified_time DESC, id DESC LIMIT %s",
                    (LIMIT * OVERFETCH,),
                )
                candidates = cur.fetchall()
    finally:
        hconn.close()

    gllue_ids = [int(r["resume_source_id"]) for r in candidates if str(r.get("resume_source_id") or "").isdigit()]
    attachments = []
    if gllue_ids:
        gconn = gllue_connect()
        try:
            for i in range(0, len(gllue_ids), 800):
                ids = gllue_ids[i:i+800]
                ph = ", ".join(["%s"] * len(ids))
                with gconn.cursor() as cur:
                    cur.execute(
                        f"SELECT id, external_id, uuidname, ext, dateAdded, real_preview_path, originpath, tag, originname "
                        f"FROM attachment WHERE type='candidate' AND active=1 AND external_id IN ({ph})",
                        ids,
                    )
                    attachments.extend(cur.fetchall())
        finally:
            gconn.close()

    by_candidate = defaultdict(list)
    for row in attachments:
        by_candidate[row.get("external_id")].append(row)

    samples = []
    seen_ext = set()
    for cand in candidates:
        rows = by_candidate.get(int(cand["resume_source_id"]))
        if not rows:
            continue
        best = pick_best(rows)
        path, source_label, ext = resolve_path(best)
        ext = (ext or "").lower().lstrip(".")
        if ext not in ALLOWED_EXTS or not path or not os.path.exists(path):
            continue
        size = os.path.getsize(path)
        if size <= 0 or size > MAX_BYTES:
            continue
        # Prefer a small amount of ext diversity in the first rows.
        if len(samples) < len(ALLOWED_EXTS) and ext in seen_ext and any((s["ext"] not in seen_ext) for s in samples):
            pass
        with open(path, "rb") as fh:
            content_b64 = base64.b64encode(fh.read()).decode("ascii")
        seen_ext.add(ext)
        samples.append({
            "resume_id": str(cand["id"]),
            "gllue_candidate_id": str(cand["resume_source_id"]),
            "candidate_name": cand.get("name") or "",
            "current_enterprise": cand.get("current_enterprise") or "",
            "current_position": cand.get("current_position") or "",
            "attachment_id": str(best.get("id") or ""),
            "filename": best.get("originname") or f"{best.get('uuidname')}.{ext}",
            "ext": ext,
            "source_label": source_label,
            "size": size,
            "content_b64": content_b64,
        })
        if len(samples) >= LIMIT:
            break

    print(json.dumps({"sample_count": len(samples), "samples": samples}, ensure_ascii=False))


main()
"""


def _redact(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
    value = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[PHONE]", value)
    value = re.sub(r"\b\d{15}(?:\d{2}[0-9Xx])?\b", "[ID]", value)
    value = re.sub(r"(姓名|Name)\s*[:：]?\s*[\u4e00-\u9fffA-Za-z .]{1,20}", r"\1：[NAME]", value)
    return value


def _remote_script(limit: int, overfetch: int, max_bytes: int, sample_mode: str) -> str:
    return (
        REMOTE_COLLECTOR
        .replace("__LIMIT__", str(limit))
        .replace("__OVERFETCH__", str(overfetch))
        .replace("__MAX_BYTES__", str(max_bytes))
        .replace("__SAMPLE_MODE__", str(sample_mode))
    )


def _collect_remote_samples(args: argparse.Namespace) -> dict[str, Any]:
    command = "python3 - <<'PY'\n" + _remote_script(args.limit, args.overfetch, args.max_bytes, args.sample_mode) + "\nPY"
    proc = subprocess.run(
        [
            "ssh",
            "-i",
            str(args.key_path),
            "-p",
            str(args.port),
            f"{args.user}@{args.host}",
            command,
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=args.timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"remote collector failed exit={proc.returncode}: {proc.stderr.strip()}")
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return json.loads(proc.stdout)


def _suspicious_company_names(company_names: list[str]) -> list[str]:
    suspicious = []
    for name in company_names:
        compact = re.sub(r"\s+", "", name)
        if re.search(r"^(?:对接|擅长|负责|推动|协同|建立|维护|覆盖)", compact):
            suspicious.append(name)
        elif re.search(r"核心医院|三甲医院|重点医院|医药健康|医疗渠道|客户资源|资源维护", compact):
            suspicious.append(name)
        elif len(compact) > 45:
            suspicious.append(name)
    return suspicious


CORPORATE_SUFFIX_RE = re.compile(
    r"\b(?:co\.?|company|ltd\.?|limited|inc\.?|pharmaceuticals?|biopharmaceutical|biotechnology|"
    r"clinical development services|medical research|hospital|university|gmbh|aps)\b",
    re.IGNORECASE,
)


def _looks_like_hard_company_pollution(name: str) -> bool:
    value = re.sub(r"\s+", " ", str(name or "").strip())
    ascii_value = re.sub(r"^[\d\s.\-)）(（]+", "", value)
    ascii_value = re.sub(r"^[•▪■◦‣⁃\-\*\uf06e\uf0d8\uf0b7]+\s*", "", ascii_value)
    if _suspicious_company_names([name]) and not CORPORATE_SUFFIX_RE.search(value):
        return True
    if re.search(
        r"^(?:be responsible|responsible|resposible|in charge of|support|provide|develop|build|manage|"
        r"contract sign off|evaluated|reported|receive the inspection|ability and willingness|i want to|spot methods|lead one|make the)\b",
        ascii_value,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        r"\b(?:hospital|hospitals)\b.*\b(?:sales|strategy|channel|listing|performance|maximi[sz]e|minimi[sz]e|"
        r"establish|access|target|achievement|coverage|standardize|standardized|administration|industry)\b",
        ascii_value,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        r"\b(?:sales|strategy|channel|listing|performance|maximi[sz]e|minimi[sz]e|establish|access|target|"
        r"achievement|coverage|standardize|standardized)\b.*\b(?:hospital|hospitals)\b",
        ascii_value,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        r"\b(?:company|pharmaceutical ltd|pharmaceutical co)\b.*\b(?:headquarter|sales|products?|department|"
        r"reporting|responsible|resposible)\b",
        ascii_value,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"\b(?:self-company|hcp360|micro-targeting|e-commerce platform|key project management team)\b", ascii_value, re.IGNORECASE):
        return True
    return False


def _classify_company_names(company_names: list[str]) -> dict[str, list[str]]:
    hard: list[str] = []
    review: list[str] = []
    for name in company_names:
        compact = re.sub(r"\s+", "", str(name or ""))
        if not compact:
            continue
        if _looks_like_hard_company_pollution(name):
            hard.append(name)
            continue
        if len(compact) > 36:
            if CORPORATE_SUFFIX_RE.search(str(name or "")):
                review.append(name)
            else:
                hard.append(name)
    return {"hard": hard, "review": review}


def _audit_sample(sample: dict[str, Any]) -> dict[str, Any]:
    content = base64.b64decode(sample["content_b64"])
    filename = sample["filename"]
    parse_filename = filename
    suffix = Path(str(parse_filename or "")).suffix.lower().lstrip(".")
    sample_ext = str(sample.get("ext") or "").lower().lstrip(".")
    if sample_ext in {"pdf", "docx", "txt", "md"} and suffix != sample_ext:
        parse_filename = f"{Path(str(filename or 'resume')).stem or 'resume'}.{sample_ext}"
    text = extract_uploaded_text(parse_filename, content)
    parsed = parse_resume_for_report(text)
    quality = parsed.get("quality") if isinstance(parsed.get("quality"), dict) else {}
    data = {
        "candidate_name": sample.get("candidate_name") or "",
        "current_company": sample.get("current_enterprise") or "",
        "current_title": sample.get("current_position") or "",
        "original_resume": text,
        "parsed_resume": parsed,
    }
    ctx = build_placeholder_context(data, {"brand_id": "tstar"})
    groups = ctx["appendix_blocks"]["experience_groups"]
    company_names = [str(group.get("company") or "") for group in groups]
    role_count = sum(len(group.get("roles") or []) for group in groups)
    project_count = len(ctx["appendix_blocks"].get("projects") or [])
    education_count = len(ctx["appendix_blocks"].get("education") or [])
    personal_count = len(ctx.get("personal_info_rows") or [])
    company_classification = _classify_company_names(company_names)
    hard_suspicious = company_classification["hard"]
    review_companies = company_classification["review"]
    warnings = []
    if quality.get("status") == "needs_ocr":
        warnings.append("needs_ocr")
    elif quality.get("status") == "low_confidence":
        warnings.append("low_text_quality")
    if not company_names and project_count == 0:
        warnings.append("no_work_company")
    if role_count == 0 and project_count == 0:
        warnings.append("no_work_role")
    if hard_suspicious:
        warnings.append("hard_suspicious_company_name")
    if review_companies:
        warnings.append("review_company_name")
    if personal_count == 0:
        warnings.append("no_personal_info")
    return {
        "resume_id": sample["resume_id"],
        "attachment_id": sample["attachment_id"],
        "filename": _redact(filename),
        "ext": sample["ext"],
        "source_label": sample["source_label"],
        "size": sample["size"],
        "char_count": len(text),
        "line_count": len([line for line in text.splitlines() if line.strip()]),
        "company_names": [_redact(name) for name in company_names],
        "role_count": role_count,
        "project_count": project_count,
        "education_count": education_count,
        "personal_info_count": personal_count,
        "quality": quality,
        "suspicious_company_names": [_redact(name) for name in hard_suspicious + review_companies],
        "hard_suspicious_company_names": [_redact(name) for name in hard_suspicious],
        "review_company_names": [_redact(name) for name in review_companies],
        "warnings": warnings,
        "redacted_head": _redact("\n".join(text.splitlines()[:18])),
    }


def _write_report(results: list[dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"hunter_parser_sample_{stamp}.json"
    summary = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sample_count": len(results),
        "warning_counts": {},
        "results": results,
    }
    counts: dict[str, int] = {}
    for item in results:
        for warning in item.get("warnings") or []:
            counts[warning] = counts.get(warning, 0) + 1
    summary["warning_counts"] = counts
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample Hunter resume attachments and audit parser quality without storing raw resumes.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--overfetch", type=int, default=40)
    parser.add_argument("--max-bytes", type=int, default=5 * 1024 * 1024)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--key-path", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "parser_audit")
    parser.add_argument("--sample-mode", choices=("latest", "spread"), default="latest")
    args = parser.parse_args()

    payload = _collect_remote_samples(args)
    results = []
    for sample in payload.get("samples") or []:
        try:
            results.append(_audit_sample(sample))
        except Exception as exc:
            results.append({
                "resume_id": sample.get("resume_id"),
                "attachment_id": sample.get("attachment_id"),
                "filename": _redact(sample.get("filename") or ""),
                "ext": sample.get("ext"),
                "warnings": ["parser_exception"],
                "error": str(exc),
            })
    report_path = _write_report(results, args.output_dir)
    warning_counts: dict[str, int] = {}
    for item in results:
        for warning in item.get("warnings") or []:
            warning_counts[warning] = warning_counts.get(warning, 0) + 1
    print(json.dumps({
        "sample_count": len(results),
        "warning_counts": warning_counts,
        "report_path": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
