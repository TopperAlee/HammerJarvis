from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def stable_document_id(path: Path) -> str:
    resolved = path.resolve()
    stat = resolved.stat()
    raw = f"{resolved.as_posix().lower()}:{stat.st_size}:{stat.st_mtime_ns}"
    return f"document:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


@dataclass
class Document:
    id: str
    filename: str
    path: str
    type: str
    mime_type: str | None
    size: int
    created_at: str
    modified_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        document_type: str,
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Document":
        resolved = Path(path).resolve()
        stat = resolved.stat()
        detected_mime = mime_type or mimetypes.guess_type(str(resolved))[0]
        return cls(
            id=stable_document_id(resolved),
            filename=resolved.name,
            path=str(resolved),
            type=document_type,
            mime_type=detected_mime,
            size=stat.st_size,
            created_at=_iso_timestamp(stat.st_ctime),
            modified_at=_iso_timestamp(stat.st_mtime),
            metadata=metadata or {},
        )


@dataclass
class DocumentContent:
    text: str
    page_count: int = 0
    has_text_layer: bool = False
    extracted_with: str = ""
    language: str | None = None
    warnings: list[str] = field(default_factory=list)
