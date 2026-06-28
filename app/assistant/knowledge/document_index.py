import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def document_record(
    path: Path,
    chunks: list[dict[str, Any]],
    *,
    original_name: str | None = None,
    stored_name: str | None = None,
    mime_type: str | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
    source_type: str = "local_path",
    extraction_status: str = "indexed",
    extraction_message: str | None = None,
) -> dict[str, Any]:
    resolved = path.resolve()
    stat = resolved.stat()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "document_id": hashlib.sha256(str(resolved).encode("utf-8")).hexdigest(),
        "name": original_name or resolved.name,
        "path": str(resolved),
        "extension": resolved.suffix.lower(),
        "original_name": original_name or resolved.name,
        "stored_name": stored_name,
        "mime_type": mime_type or "application/octet-stream",
        "size_bytes": size_bytes if size_bytes is not None else stat.st_size,
        "sha256": sha256,
        "uploaded_at": now if source_type == "upload" else None,
        "indexed_at": now,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        "chunk_count": len(chunks),
        "extraction_status": extraction_status,
        "extraction_message": extraction_message,
        "source_type": source_type,
    }
