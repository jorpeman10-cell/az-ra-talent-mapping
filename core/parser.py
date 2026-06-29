"""
简历解析模块 - 从 PDF/DOCX/TXT 提取文本
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import docx


def extract_resume_text(path: str | Path) -> str:
    """根据文件类型提取简历文本"""
    resume_path = Path(path)
    suffix = resume_path.suffix.lower()

    if suffix == ".docx":
        return clean_text(extract_docx_text(resume_path))
    if suffix == ".pdf":
        return clean_text(extract_pdf_text(resume_path))
    if suffix in {".txt", ".md"}:
        return clean_text(resume_path.read_text(encoding="utf-8", errors="ignore"))

    raise ValueError(f"Unsupported resume format: {suffix}. Use DOCX, PDF, TXT, or MD.")


def extract_docx_text(path: str | Path) -> str:
    """从 DOCX 提取文本"""
    doc = docx.Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def extract_pdf_text(path: str | Path) -> str:
    """从 PDF 提取文本"""
    from pypdf import PdfReader

    text_parts = []
    reader = PdfReader(str(path))
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n\n".join(text_parts)


def clean_text(text: str) -> str:
    """清理文本中的多余空白和特殊字符"""
    if not text:
        return ""

    # 统一换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 移除多余空白行（最多保留一个空行）
    lines = text.split("\n")
    cleaned_lines = []
    prev_empty = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if not prev_empty:
                cleaned_lines.append("")
            prev_empty = True
        else:
            cleaned_lines.append(stripped)
            prev_empty = False

    return "\n".join(cleaned_lines)


# 便捷函数
def extract_uploaded_text(filename: str, content: bytes) -> str:
    """Extract text from uploaded DOCX/TXT/MD/PDF bytes."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        document = docx.Document(BytesIO(content))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        return clean_text("\n\n".join(paragraphs))
    if suffix in {".txt", ".md"}:
        return clean_text(content.decode("utf-8", errors="ignore"))
    if suffix == ".pdf":
        from pypdf import PdfReader

        text_parts = []
        reader = PdfReader(BytesIO(content))
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return clean_text("\n\n".join(text_parts))
    raise ValueError(f"Unsupported upload format: {suffix}. Use DOCX, PDF, TXT, or MD.")


__all__ = [
    "extract_resume_text",
    "extract_docx_text",
    "extract_pdf_text",
    "extract_uploaded_text",
    "clean_text",
]
