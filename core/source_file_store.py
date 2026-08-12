from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SOURCE_FILE_RE = re.compile(r"^rf_[a-f0-9]{32}$")
SUPPORTED_SOURCE_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class SourceFileStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.source_files_dir = self.data_dir / "source_files"
        self.source_files_dir.mkdir(parents=True, exist_ok=True)

    def create(self, filename: str, content: bytes, mime_type: str = "") -> dict[str, Any]:
        safe_name = Path(str(filename or "resume")).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_SOURCE_SUFFIXES:
            allowed = ", ".join(sorted(SUPPORTED_SOURCE_SUFFIXES))
            raise ValueError(f"Unsupported source file format: {suffix or '(none)'}. Use {allowed}.")
        if not content:
            raise ValueError("Source file content is required")

        content_hash = hashlib.sha256(content).hexdigest()
        source_file_id = f"rf_{content_hash[:32]}"
        binary_path = self.source_files_dir / f"{source_file_id}{suffix}"
        metadata_path = self._metadata_path(source_file_id)
        if not binary_path.exists():
            binary_path.write_bytes(content)

        record = {
            "source_file_id": source_file_id,
            "content_hash": content_hash,
            "file_name": safe_name,
            "suffix": suffix,
            "mime_type": str(mime_type or ""),
            "byte_count": len(content),
            "stored_name": binary_path.name,
            "created_at": datetime.now(UTC).isoformat(),
        }
        if metadata_path.exists():
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            record["created_at"] = existing.get("created_at") or record["created_at"]
        metadata_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def load(self, source_file_id: str) -> dict[str, Any]:
        metadata_path = self._metadata_path(source_file_id)
        if not metadata_path.exists():
            raise FileNotFoundError(source_file_id)
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def path_for(self, source_file_id: str) -> Path:
        record = self.load(source_file_id)
        path = self.source_files_dir / Path(str(record["stored_name"])).name
        if not path.exists():
            raise FileNotFoundError(source_file_id)
        return path

    def _metadata_path(self, source_file_id: str) -> Path:
        if not SOURCE_FILE_RE.fullmatch(str(source_file_id or "")):
            raise ValueError("Invalid source_file_id")
        return self.source_files_dir / f"{source_file_id}.json"


__all__ = ["SourceFileStore", "SUPPORTED_SOURCE_SUFFIXES"]
