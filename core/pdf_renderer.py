from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .placeholder_report import build_placeholder_context


TSTAR_CN = "\u6cf0\u4f26\u4ed5"
PAGE_W = 595
PAGE_H = 842
LEFT = 46
RIGHT = 549
BOTTOM = 54


class PdfReportRenderer:
    def __init__(self, brand_config: dict[str, Any]) -> None:
        self.brand_config = brand_config
        self.primary = self._brand_color("primary_color", "F7B500")
        self.accent = self._brand_color("accent_color", "2F5597")
        self.black = "111827"
        self.border = "D8DEE8"
        self.gray = "6B7280"
        self.pages: list[list[str]] = []
        self.commands: list[str] = []
        self.y = 790.0

    def render(self, data: dict[str, Any], output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if self._render_from_html(data, output):
            return output
        output.write_bytes(self._build_pdf(data))
        return output

    def _render_from_html(self, data: dict[str, Any], output: Path) -> bool:
        chrome = self._chrome_path()
        if not chrome:
            return False
        from .html_renderer import write_report_html

        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "report.html"
            write_report_html(data, self.brand_config, html_path)
            try:
                subprocess.run(
                    [
                        chrome,
                        "--headless=new",
                        "--disable-gpu",
                        f"--print-to-pdf={output}",
                        "--print-to-pdf-no-header",
                        str(html_path),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=45,
                )
            except Exception:
                return False
        return output.exists() and output.stat().st_size > 0

    def _chrome_path(self) -> str:
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return ""

    def _build_pdf(self, data: dict[str, Any]) -> bytes:
        self.pages = []
        self.commands = []
        self.y = 790.0
        self._draw_report(data)
        self._finish_page(data)
        streams = ["\n".join(page).encode("ascii") for page in self.pages]

        page_count = len(streams)
        first_page_obj = 6
        kids = " ".join(f"{first_page_obj + index * 2} 0 R" for index in range(page_count))
        objects: list[bytes] = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii"),
            (
                b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light "
                b"/Encoding /UniGB-UCS2-H /DescendantFonts [4 0 R] >>"
            ),
            (
                b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
                b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 2 >> >>"
            ),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
        for index, stream in enumerate(streams):
            page_obj = first_page_obj + index * 2
            content_obj = page_obj + 1
            objects.append(
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                    f"/Resources << /Font << /F1 3 0 R /F2 5 0 R >> >> "
                    f"/Contents {content_obj} 0 R >>"
                ).encode("ascii")
            )
            objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")

        chunks = [b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"]
        offsets = [0]
        for obj_index, obj in enumerate(objects, start=1):
            offsets.append(sum(len(chunk) for chunk in chunks))
            chunks.append(f"{obj_index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
        xref_offset = sum(len(chunk) for chunk in chunks)
        chunks.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
        for offset in offsets[1:]:
            chunks.append(f"{offset:010d} 00000 n \n".encode("ascii"))
        chunks.append(
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
        )
        return b"".join(chunks)

    def _draw_report(self, data: dict[str, Any]) -> None:
        self._apply_style(data)
        ctx = build_placeholder_context(data, self.brand_config)

        self._rect(LEFT, 735, 114, 70, self.primary, fill=True)
        self._text(str(ctx["brand_name"]), 62, 779, 22, "FFFFFF")
        self._text(TSTAR_CN, 78, 752, 12, "111111")
        self._text(self._style_label(data), 178, 804, 8.5, self.accent)
        self._text("Candidate Referral Report", 178, 786, 24, self.black)
        y = 762
        for label, value in [
            ("Candidate", ctx["candidate_name"]),
            ("Target Role", ctx["target_role"]),
            ("Client", ctx["client_company"]),
            ("Current", ctx["current_summary"]),
        ]:
            self._text(f"{label}: {value}", 178, y, 10, self.black)
            y -= 15
        self._rect(LEFT, 716, 503, 14, self.primary, fill=True)
        self.y = 690

        self._section("Recommendation Summary", [
            ("Motivation", ctx["motivation"]),
            ("Role Fit", ctx["role_fit"]),
        ])
        self._section("Consultant Assessment", [
            ("Strengths", ctx["strengths_summary"]),
            ("Risks / Questions", ctx["risk_notes"]),
        ])
        self._heading("Candidate Profile")
        for label, value in ctx.get("personal_info_rows", [])[:8]:
            self._paragraph(f"{label}: {value}", x=58, size=9.5, width=455)
        if ctx.get("salary_info"):
            self._paragraph(f"Salary: {ctx['salary_info']}", x=58, size=9.5, width=455)

        if ctx["work_experience_items"]:
            self._heading("Work Experience")
            for item in ctx["work_experience_items"][:8]:
                self._paragraph(str(item), x=58, size=9.2, width=455)

        if ctx["job_description"]:
            self._heading("Role Requirement Notes")
            self._paragraph(ctx["job_description"], x=58, size=9.2, width=455)

        self._finish_page(data)
        self.commands = []
        self.y = 790
        self._heading("Original Resume Appendix / \u539f\u59cb\u7b80\u5386\u9644\u5f55")
        original_resume = ctx["appendix_resume"] or "No original resume text was found. Please re-upload the resume file."
        self._original_resume(original_resume)

    def _section(self, title: str, rows: list[tuple[str, str]]) -> None:
        self._heading(title)
        for label, value in rows:
            wrapped = self._wrap(value or "-", 72)
            height = max(34, 16 + 13 * len(wrapped))
            self._ensure_space(height + 8)
            y_bottom = self.y - height + 11
            self._rect(LEFT, y_bottom, 503, height, self.border, fill=False)
            self.commands.append("q " + self._stroke(self.border) + f" 145 {y_bottom:.1f} m 145 {y_bottom + height:.1f} l S Q")
            self._text(label, 55, self.y - 4, 9, self.accent)
            line_y = self.y - 4
            for line in wrapped:
                self._text(line, 154, line_y, 9.5, self.black)
                line_y -= 13
            self.y -= height + 8

    def _original_resume(self, text: str) -> None:
        for raw_line in str(text).splitlines():
            line = raw_line.strip()
            if not line:
                self.y -= 8
                continue
            self._paragraph(line, x=58, size=8.8, width=455)

    def _heading(self, title: str) -> None:
        self._ensure_space(32)
        self._text(title, LEFT, self.y, 14, self.accent)
        self.y -= 20

    def _paragraph(self, text: str, x: float, size: float, width: float) -> None:
        for line in self._wrap(text, max(20, int(width / (size * 0.55)))):
            self._ensure_space(16)
            self._text(line, x, self.y, size, self.black)
            self.y -= 14
        self.y -= 2

    def _ensure_space(self, needed: float) -> None:
        if self.y - needed >= BOTTOM:
            return
        self._finish_page({})
        self.commands = []
        self.y = 790
        self._text("Candidate Referral Report (continued)", LEFT, self.y, 13, self.accent)
        self.y -= 24

    def _finish_page(self, data: dict[str, Any]) -> None:
        if not self.commands:
            return
        page_number = len(self.pages) + 1
        self._text(f"Draft for consultant review | page {page_number}", 382, 38, 8.5, self.gray)
        self.pages.append(self.commands)

    def _text(self, value: str, x: float, y: float, size: float, color: str) -> None:
        current_x = x
        for chunk, font_name in self._font_chunks(value):
            if not chunk:
                continue
            if font_name == "F2":
                self.commands.extend([
                    "BT",
                    self._fill(color),
                    f"/F2 {size:.1f} Tf",
                    f"1 0 0 1 {current_x:.1f} {y:.1f} Tm",
                    f"({self._escape_literal(chunk)}) Tj",
                    "ET",
                ])
            else:
                self.commands.extend([
                    "BT",
                    self._fill(color),
                    f"/F1 {size:.1f} Tf",
                    f"1 0 0 1 {current_x:.1f} {y:.1f} Tm",
                    f"<{chunk.encode('utf-16-be', errors='ignore').hex().upper()}> Tj",
                    "ET",
                ])
            current_x += self._measure(chunk, size, font_name)

    def _font_chunks(self, value: str) -> list[tuple[str, str]]:
        chunks: list[tuple[str, str]] = []
        current = ""
        current_font = ""
        for char in str(value):
            font = "F2" if 32 <= ord(char) <= 126 else "F1"
            if current and font != current_font:
                chunks.append((current, current_font))
                current = char
                current_font = font
            else:
                current += char
                current_font = font
        if current:
            chunks.append((current, current_font))
        return chunks

    def _measure(self, value: str, size: float, font_name: str) -> float:
        if font_name == "F2":
            return len(value) * size * 0.52
        return len(value) * size

    def _escape_literal(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def _rect(self, x: float, y: float, w: float, h: float, color: str, fill: bool) -> None:
        op = "f" if fill else "S"
        color_op = self._fill(color) if fill else self._stroke(color)
        self.commands.append(f"q {color_op} {x:.1f} {y:.1f} {w:.1f} {h:.1f} re {op} Q")

    def _fill(self, color: str) -> str:
        r, g, b = self._rgb(color)
        return f"{r:.4f} {g:.4f} {b:.4f} rg"

    def _stroke(self, color: str) -> str:
        r, g, b = self._rgb(color)
        return f"{r:.4f} {g:.4f} {b:.4f} RG 0.6 w"

    def _rgb(self, color: str) -> tuple[float, float, float]:
        value = color.replace("#", "")
        return int(value[0:2], 16) / 255, int(value[2:4], 16) / 255, int(value[4:6], 16) / 255

    def _brand_color(self, key: str, fallback: str) -> str:
        return str(self.brand_config.get("branding", {}).get(key, fallback)).replace("#", "").upper()

    def _apply_style(self, data: dict[str, Any]) -> None:
        style = str(data.get("report_style") or "tstar_warm")
        if style == "consulting_blue":
            self.primary = "0B1F3A"
            self.accent = "1F4E79"
            self.black = "071A2F"
            self.border = "CED6E0"
            return
        self.primary = self._brand_color("primary_color", "F7B500")
        self.accent = self._brand_color("accent_color", "2F5597")
        self.black = "111827"
        self.border = "D8DEE8"

    def _style_label(self, data: dict[str, Any]) -> str:
        return "Consulting Blue" if str(data.get("report_style") or "") == "consulting_blue" else "T-STAR Warm Gold"

    def _value(self, data: dict[str, Any], key: str, fallback: str = "-") -> str:
        value = data.get(key)
        return fallback if value is None or value == "" else str(value)

    def _compact_join(self, values: list[Any]) -> str:
        return " / ".join(str(value) for value in values if value)

    def _wrap(self, text: str, limit: int) -> list[str]:
        normalized = re.sub(r"\s+", " ", str(text)).strip()
        if not normalized:
            return ["-"]
        lines: list[str] = []
        current = ""
        current_width = 0
        for char in normalized:
            char_width = 2 if ord(char) > 127 else 1
            if current and current_width + char_width > limit:
                lines.append(current)
                current = char
                current_width = char_width
            else:
                current += char
                current_width += char_width
        if current:
            lines.append(current)
        return lines

    def _truncate(self, text: str, limit: int) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        return normalized if len(normalized) <= limit else normalized[:limit].rstrip() + "..."

    def _list_items(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]


__all__ = ["PdfReportRenderer"]
