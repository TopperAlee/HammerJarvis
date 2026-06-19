from pathlib import Path
from typing import Any


def document_record(path: Path, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "document_id": str(abs(hash(str(resolved)))),
        "name": resolved.name,
        "path": str(resolved),
        "extension": resolved.suffix.lower(),
        "chunk_count": len(chunks),
    }
