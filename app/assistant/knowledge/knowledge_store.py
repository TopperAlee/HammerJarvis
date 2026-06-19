import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.assistant.knowledge.chunker import chunk_text
from app.assistant.knowledge.document_index import document_record
from app.tools.files.content_extractors import extract_text
from app.tools.files.path_safety import _is_relative_to


SUPPORTED_KNOWLEDGE_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


class KnowledgeStore:
    def __init__(self) -> None:
        self.path = Path(os.getenv("KNOWLEDGE_STORE_FILE", "app/data/knowledge/knowledge_index.json"))
        self.chunk_size = _int_env("KNOWLEDGE_CHUNK_SIZE", 1200)
        self.chunk_overlap = _int_env("KNOWLEDGE_CHUNK_OVERLAP", 150)

    def status(self) -> dict[str, Any]:
        data = self._load()
        return {
            "enabled": os.getenv("KNOWLEDGE_ENABLED", "true").strip().lower() == "true",
            "store_file": str(self.path),
            "document_count": len(data["documents"]),
            "chunk_count": len(data["chunks"]),
            "allowed_dirs": [str(path) for path in _allowed_dirs()],
        }

    def index_text_file(self, path: str | Path) -> dict[str, Any]:
        target = Path(path).expanduser().resolve()
        blocked = _blocked_path_reason(target)
        if blocked:
            return {"indexed": False, "blocked": True, "reason": blocked, "path": str(target)}
        extracted = extract_text(target)
        if extracted.get("skipped") or extracted.get("error"):
            return {"indexed": False, "error": True, "reason": extracted.get("reason"), "message": extracted.get("message"), "path": str(target)}
        chunks = chunk_text(str(extracted.get("text", "")), self.chunk_size, self.chunk_overlap)
        document = document_record(target, chunks)
        now = _now()
        data = self._load()
        data["documents"] = [item for item in data["documents"] if item.get("document_id") != document["document_id"]]
        data["chunks"] = [item for item in data["chunks"] if item.get("document_id") != document["document_id"]]
        data["documents"].append({**document, "indexed_at": now})
        for chunk in chunks:
            data["chunks"].append({**chunk, "document_id": document["document_id"], "document_name": document["name"], "path": document["path"]})
        self._save(data)
        return {"indexed": True, "document": document, "chunk_count": len(chunks), "message": f"Dokument indexiert: {document['name']}"}

    def index_directory(self, path: str | Path) -> dict[str, Any]:
        root = Path(path).expanduser().resolve()
        blocked = _blocked_path_reason(root, allow_directory=True)
        if blocked:
            return {"indexed": False, "blocked": True, "reason": blocked, "path": str(root)}
        indexed = []
        skipped = []
        for file in root.rglob("*"):
            if not file.is_file():
                continue
            result = self.index_text_file(file)
            if result.get("indexed"):
                indexed.append(result)
            else:
                skipped.append(result)
        return {"indexed": True, "count": len(indexed), "indexed_files": indexed, "skipped": skipped}

    def search_knowledge(self, query: str, limit: int | None = None) -> dict[str, Any]:
        limit = limit or _int_env("KNOWLEDGE_MAX_RESULTS", 8)
        terms = _terms(query)
        results = []
        for chunk in self._load()["chunks"]:
            text = str(chunk.get("text", ""))
            lowered = text.lower()
            score = sum(lowered.count(term) for term in terms)
            if score > 0:
                results.append({**chunk, "score": score, "snippet": _snippet(text, terms)})
        results.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("document_name"))))
        return {"query": query, "count": len(results), "results": results[:limit], "sources": _sources(results[:limit])}

    def get_document_chunks(self, document_id: str) -> dict[str, Any]:
        chunks = [item for item in self._load()["chunks"] if item.get("document_id") == document_id]
        return {"document_id": document_id, "count": len(chunks), "chunks": chunks}

    def list_documents(self) -> dict[str, Any]:
        documents = self._load()["documents"]
        return {"count": len(documents), "documents": documents}

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {"documents": [], "chunks": []}
        return {
            "documents": data.get("documents", []) if isinstance(data.get("documents"), list) else [],
            "chunks": data.get("chunks", []) if isinstance(data.get("chunks"), list) else [],
        }

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _allowed_dirs() -> list[Path]:
    configured = os.getenv("KNOWLEDGE_ALLOWED_DIRS", os.getenv("FILE_SEARCH_ALLOWED_DIRS", "workspace/exports"))
    return [Path(os.path.expandvars(part.strip())).expanduser().resolve() for part in configured.split(";") if part.strip()]


def _blocked_path_reason(path: Path, allow_directory: bool = False) -> str | None:
    lowered = str(path).lower()
    if path.name.lower() == ".env" or "app\\secrets" in lowered or "app/secrets" in lowered:
        return "secret_path"
    if not allow_directory and path.suffix.lower() not in SUPPORTED_KNOWLEDGE_EXTENSIONS:
        return "unsupported_file_type"
    if not any(_is_relative_to(path, allowed) for allowed in _allowed_dirs()):
        return "outside_allowed_dirs"
    return None


def _terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[\wäöüÄÖÜß]+", query.lower()) if len(term) > 2]


def _snippet(text: str, terms: list[str]) -> str:
    lowered = text.lower()
    positions = [lowered.find(term) for term in terms if term in lowered]
    start = max(0, min(positions or [0]) - 80)
    return text[start : start + 240].strip()


def _sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    sources = []
    for item in results:
        key = item.get("document_id")
        if key in seen:
            continue
        seen.add(key)
        sources.append({"document_id": key, "name": item.get("document_name"), "path": item.get("path")})
    return sources


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
