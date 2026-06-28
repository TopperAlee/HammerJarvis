"""Local JSON-backed knowledge store with safe upload primitives."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.assistant.knowledge.chunker import chunk_text
from app.assistant.knowledge.document_index import document_record
from app.assistant.knowledge.storage import (
    SUPPORTED_KNOWLEDGE_EXTENSIONS,
    CrossProcessFileLock,
    knowledge_storage_paths,
    max_upload_bytes,
    safe_stored_name,
    sha256_bytes,
    sha256_file,
    validate_upload_filename,
)
from app.tools.files.content_extractors import extract_text
from app.tools.files.path_safety import _is_relative_to


class IndexRecoveryError(RuntimeError):
    """Raised when an existing index and its backup cannot be safely recovered."""


class KnowledgeStore:
    """Stores local document metadata and extracted chunks without exposing contents in logs."""

    _lock = threading.RLock()

    def __init__(self) -> None:
        paths = knowledge_storage_paths()
        self.path = paths.index_file
        self.backup_path = paths.backup_file
        self.lock_path = paths.lock_file
        self.upload_dir = paths.upload_dir
        self.chunk_size = _int_env("KNOWLEDGE_CHUNK_SIZE", 1200)
        self.chunk_overlap = _int_env("KNOWLEDGE_CHUNK_OVERLAP", 150)
        self._reconcile_pending_deletes()

    def status(self) -> dict[str, Any]:
        try:
            data = self._load()
        except IndexRecoveryError:
            return {
                "enabled": os.getenv("KNOWLEDGE_ENABLED", "true").strip().lower() == "true",
                "store_file": str(self.path),
                "upload_dir": str(self.upload_dir),
                "document_count": 0,
                "chunk_count": 0,
                "allowed_dirs": [str(path) for path in _allowed_dirs()],
                "error": True,
                "reason": "index_recovery_failed",
            }
        return {
            "enabled": os.getenv("KNOWLEDGE_ENABLED", "true").strip().lower() == "true",
            "store_file": str(self.path),
            "upload_dir": str(self.upload_dir),
            "document_count": len(data["documents"]),
            "chunk_count": len(data["chunks"]),
            "allowed_dirs": [str(path) for path in _allowed_dirs()],
        }

    def store_upload(self, filename: str, content: bytes, mime_type: str | None = None) -> dict[str, Any]:
        """Persist one validated upload once; duplicate SHA-256 values reuse the existing document."""

        valid, original_name, reason = validate_upload_filename(filename)
        if not valid:
            return {"stored": False, "error": True, "reason": reason}
        if not content:
            return {"stored": False, "error": True, "reason": "empty_file"}
        if len(content) > max_upload_bytes():
            return {"stored": False, "error": True, "reason": "file_too_large"}

        extension = Path(original_name).suffix.lower()
        if extension == ".pdf" and not content.startswith(b"%PDF"):
            return {"stored": False, "error": True, "reason": "invalid_pdf_header"}

        digest = sha256_bytes(content)
        try:
            with self._index_guard():
                data = self._load_unlocked()
                duplicate = next(
                    (item for item in data["documents"] if item.get("source_type") == "upload" and item.get("sha256") == digest),
                    None,
                )
                if duplicate:
                    return {"stored": True, "duplicate": True, "document": duplicate, "message": "Datei bereits vorhanden."}

                try:
                    self.upload_dir.mkdir(parents=True, exist_ok=True)
                except OSError:
                    return {"stored": False, "error": True, "reason": "upload_write_failed"}
                stored_name = safe_stored_name(extension)
                target = (self.upload_dir / stored_name).resolve()
                if not _is_relative_to(target, self.upload_dir):
                    return {"stored": False, "error": True, "reason": "unsafe_upload_path"}
                try:
                    self._write_upload_file(target, content)
                except OSError:
                    return {"stored": False, "error": True, "reason": "upload_write_failed"}
                now = _now()
                document = {
                    "document_id": _document_id(target),
                    "name": original_name,
                    "original_name": original_name,
                    "stored_name": stored_name,
                    "path": str(target),
                    "extension": extension,
                    "mime_type": mime_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream",
                    "size_bytes": len(content),
                    "sha256": digest,
                    "uploaded_at": now,
                    "indexed_at": None,
                    "modified_at": now,
                    "chunk_count": 0,
                    "extraction_status": "pending",
                    "extraction_message": "Noch nicht indexiert.",
                    "source_type": "upload",
                }
                data["documents"].append(document)
                try:
                    self._save_unlocked(data)
                except Exception:
                    self._remove_upload_after_failed_index_write(target)
                    return {"stored": False, "error": True, "reason": "index_write_failed"}
                return {"stored": True, "duplicate": False, "document": document, "message": "Datei lokal gespeichert."}
        except IndexRecoveryError:
            return _index_recovery_result("stored")

    def index_text_file(self, path: str | Path) -> dict[str, Any]:
        target = Path(path).expanduser().resolve()
        blocked = _blocked_path_reason(target)
        if blocked:
            return {"indexed": False, "blocked": True, "reason": blocked, "path": str(target)}
        return self._index_path(target, source_type="local_path")

    def index_directory(self, path: str | Path) -> dict[str, Any]:
        root = Path(path).expanduser().resolve()
        blocked = _blocked_path_reason(root, allow_directory=True)
        if blocked:
            return {"indexed": False, "blocked": True, "reason": blocked, "path": str(root)}
        indexed, skipped = [], []
        for file in root.rglob("*"):
            if not file.is_file():
                continue
            result = self.index_text_file(file)
            (indexed if result.get("indexed") else skipped).append(result)
        return {"indexed": True, "count": len(indexed), "indexed_files": indexed, "skipped": skipped}

    def get_document(self, document_id: str) -> dict[str, Any]:
        try:
            documents = self._load()["documents"]
        except IndexRecoveryError:
            return {"found": False, "error": True, "reason": "index_recovery_failed"}
        document = next((item for item in documents if item.get("document_id") == document_id), None)
        return {"found": document is not None, "document": document}

    def reindex_document(self, document_id: str) -> dict[str, Any]:
        """Re-extract an existing document without changing its upload identity."""

        try:
            with self._index_guard():
                data = self._load_unlocked()
                document = next((item for item in data["documents"] if item.get("document_id") == document_id), None)
                if not document:
                    return {"indexed": False, "error": True, "reason": "document_not_found"}
                document = dict(document)
                target = Path(str(document.get("path", ""))).resolve()
                if not target.is_file():
                    return {"indexed": False, "error": True, "reason": "source_file_missing"}
                if document.get("source_type") == "upload" and not _is_relative_to(target, self.upload_dir):
                    return {"indexed": False, "error": True, "reason": "unsafe_upload_path"}
                if document.get("source_type") == "local_path":
                    blocked = _blocked_path_reason(target)
                    if blocked:
                        return {"indexed": False, "blocked": True, "reason": blocked, "path": str(target)}
                expected_document_version = _document_version(document)
                expected_file_state = _file_state(target)
        except IndexRecoveryError:
            return _index_recovery_result("indexed")
        return self._index_path(
            target,
            source_type=str(document.get("source_type") or "local_path"),
            existing=document,
            expected_document_version=expected_document_version,
            expected_file_state=expected_file_state,
        )

    def delete_document(self, document_id: str) -> dict[str, Any]:
        """Delete index records; only uploads inside the managed upload directory may be unlinked."""

        try:
            with self._index_guard():
                data = self._load_unlocked()
                document = next((item for item in data["documents"] if item.get("document_id") == document_id), None)
                if not document:
                    return {"deleted": False, "error": True, "reason": "document_not_found"}
                target = Path(str(document.get("path", ""))).resolve()
                pending_path: Path | None = None
                if document.get("source_type") == "upload" and _is_relative_to(target, self.upload_dir) and target.is_file():
                    pending_path = self._pending_delete_path(target)
                    if pending_path is None:
                        return {"deleted": False, "error": True, "reason": "unsafe_pending_delete_path"}
                    if not self._write_pending_marker(pending_path, target, document_id):
                        return {"deleted": False, "error": True, "reason": "pending_marker_write_failed"}
                    try:
                        pending_path.parent.mkdir(parents=True, exist_ok=True)
                        target.replace(pending_path)
                    except OSError:
                        self._remove_pending_marker(pending_path)
                        return {"deleted": False, "error": True, "reason": "upload_delete_prepare_failed"}
                data["documents"] = [item for item in data["documents"] if item.get("document_id") != document_id]
                data["chunks"] = [item for item in data["chunks"] if item.get("document_id") != document_id]
                try:
                    self._save_unlocked(data)
                except Exception:
                    if pending_path is not None:
                        try:
                            pending_path.replace(target)
                        except OSError:
                            return {"deleted": False, "error": True, "reason": "delete_rollback_failed"}
                        self._remove_pending_marker(pending_path)
                    return {"deleted": False, "error": True, "reason": "index_write_failed"}
                if pending_path is not None:
                    try:
                        pending_path.unlink()
                    except OSError:
                        return {"deleted": True, "physical_file_deleted": False, "cleanup_pending": True, "document_id": document_id}
                    self._remove_pending_marker(pending_path)
                return {"deleted": True, "physical_file_deleted": pending_path is not None, "document_id": document_id}
        except IndexRecoveryError:
            return _index_recovery_result("deleted")

    def search_knowledge(self, query: str, limit: int | None = None) -> dict[str, Any]:
        limit = limit or _int_env("KNOWLEDGE_MAX_RESULTS", 8)
        terms = _terms(query)
        results = []
        try:
            chunks = self._load()["chunks"]
        except IndexRecoveryError:
            return {"query": query, "count": 0, "results": [], "sources": [], "error": True, "reason": "index_recovery_failed"}
        for chunk in chunks:
            text = str(chunk.get("text", ""))
            lowered = text.lower()
            score = sum(lowered.count(term) for term in terms)
            if score > 0:
                results.append({**chunk, "score": score, "snippet": _snippet(text, terms)})
        results.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("document_name"))))
        return {"query": query, "count": len(results), "results": results[:limit], "sources": _sources(results[:limit])}

    def get_document_chunks(self, document_id: str) -> dict[str, Any]:
        try:
            chunks = [item for item in self._load()["chunks"] if item.get("document_id") == document_id]
        except IndexRecoveryError:
            return {"document_id": document_id, "count": 0, "chunks": [], "error": True, "reason": "index_recovery_failed"}
        return {"document_id": document_id, "count": len(chunks), "chunks": chunks}

    def list_documents(self) -> dict[str, Any]:
        try:
            documents = self._load()["documents"]
        except IndexRecoveryError:
            return {"count": 0, "documents": [], "error": True, "reason": "index_recovery_failed"}
        return {"count": len(documents), "documents": documents}

    def _index_path(
        self,
        target: Path,
        *,
        source_type: str,
        existing: dict[str, Any] | None = None,
        expected_document_version: tuple[Any, ...] | None = None,
        expected_file_state: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        extracted = extract_text(target)
        if extracted.get("reason") == "ocr_required":
            chunks: list[dict[str, Any]] = []
            status = "ocr_required"
            message = "Das PDF enthält keinen extrahierbaren Text. OCR wird noch nicht unterstützt."
        elif extracted.get("skipped") or extracted.get("error"):
            return {"indexed": False, "error": True, "reason": extracted.get("reason"), "message": extracted.get("message"), "path": str(target)}
        else:
            chunks = chunk_text(str(extracted.get("text", "")), self.chunk_size, self.chunk_overlap)
            status = "ocr_required" if target.suffix.lower() == ".pdf" and not chunks else "indexed"
        message = "PDF enthält keinen extrahierbaren Text; OCR ist erforderlich." if status == "ocr_required" else None
        if extracted.get("reason") == "ocr_required":
            message = str(
                extracted.get("message")
                or "Das PDF enthält keinen extrahierbaren Text. OCR wird noch nicht unterstützt."
            )
        try:
            with self._index_guard():
                data = self._load_unlocked()
                current = _find_document(data["documents"], existing) if existing else None
                if existing and current is None:
                    return {"indexed": False, "error": True, "reason": "document_not_found"}
                if existing and expected_document_version is not None and _document_version(current) != expected_document_version:
                    return {"indexed": False, "error": True, "reason": "document_changed_during_reindex"}
                if expected_file_state is not None and _file_state(target) != expected_file_state:
                    return {"indexed": False, "error": True, "reason": "source_changed_during_reindex"}
                try:
                    stat = target.stat()
                except OSError:
                    return {"indexed": False, "error": True, "reason": "source_file_missing"}
                document = document_record(
                    target,
                    chunks,
                    original_name=str((current or existing or {}).get("original_name") or target.name),
                    stored_name=(current or existing or {}).get("stored_name"),
                    mime_type=(current or existing or {}).get("mime_type") or mimetypes.guess_type(target.name)[0],
                    size_bytes=stat.st_size,
                    sha256=(current or existing or {}).get("sha256") or sha256_file(target),
                    source_type=source_type,
                    extraction_status=status,
                    extraction_message=message,
                )
                if current or existing:
                    document["document_id"] = str((current or existing)["document_id"])
                    document["uploaded_at"] = (current or existing).get("uploaded_at")
                removed_ids = _matching_document_ids(data["documents"], document)
                data["documents"] = [item for item in data["documents"] if item.get("document_id") not in removed_ids and not _same_resolved_path(item, target)]
                data["chunks"] = [item for item in data["chunks"] if item.get("document_id") not in removed_ids]
                data["documents"].append(document)
                for chunk in chunks:
                    data["chunks"].append({**chunk, "document_id": document["document_id"], "document_name": document["name"], "path": document["path"]})
                self._save_unlocked(data)
        except IndexRecoveryError:
            return _index_recovery_result("indexed")
        return {"indexed": True, "document": document, "chunk_count": len(chunks), "message": f"Dokument indexiert: {document['name']}"}

    def _load(self) -> dict[str, Any]:
        with self._index_guard():
            return self._load_unlocked()

    @contextmanager
    def _index_guard(self):
        """Protect read-modify-write cycles across threads and local processes."""

        with self._lock:
            with CrossProcessFileLock(self.lock_path):
                yield

    def _load_unlocked(self) -> dict[str, Any]:
        data = _read_index(self.path)
        if data is not None:
            return data
        backup = _read_index(self.backup_path)
        if backup is not None:
            self._save_unlocked(backup, create_backup=False)
            return backup
        if self.path.exists() or self.backup_path.exists():
            raise IndexRecoveryError("index_recovery_failed")
        return {"documents": [], "chunks": []}

    def _save_unlocked(self, data: dict[str, Any], *, create_backup: bool = True) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if create_backup:
            current = _read_index(self.path)
            if current is not None:
                _atomic_json_write(self.backup_path, current)
        _atomic_json_write(self.path, _normalise_index(data))

    @staticmethod
    def _write_upload_file(target: Path, content: bytes) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent, prefix=".upload-", delete=False) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, target)
        except OSError:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    def _remove_upload_after_failed_index_write(self, target: Path) -> None:
        if not _is_relative_to(target, self.upload_dir):
            return
        try:
            target.unlink(missing_ok=True)
        except OSError:
            # The API returns a safe generic failure. No file contents or platform errors are exposed.
            pass

    def _pending_delete_path(self, target: Path) -> Path | None:
        """Return a managed same-volume destination, never a path derived outside uploads."""

        if not _is_relative_to(target.resolve(), self.upload_dir):
            return None
        pending_dir = self._pending_delete_directory()
        pending = (pending_dir / f"{uuid4().hex}.pending").resolve()
        return pending if _is_relative_to(pending, self.upload_dir) and pending.parent == pending_dir else None

    def _pending_delete_directory(self) -> Path:
        return (self.upload_dir / ".pending_delete").resolve()

    def _pending_marker_path(self, pending_path: Path) -> Path:
        return pending_path.with_name(f"{pending_path.name}.marker.json")

    def _write_pending_marker(self, pending_path: Path, original_path: Path, document_id: str) -> bool:
        if not self._is_safe_pending_path(pending_path) or not _is_relative_to(original_path.resolve(), self.upload_dir):
            return False
        try:
            _atomic_json_write(
                self._pending_marker_path(pending_path),
                {
                    "pending_path": str(pending_path),
                    "original_path": str(original_path.resolve()),
                    "document_id": document_id,
                },
            )
        except OSError:
            return False
        return True

    def _remove_pending_marker(self, pending_path: Path) -> None:
        marker = self._pending_marker_path(pending_path)
        if self._is_safe_pending_path(pending_path) and _is_relative_to(marker.resolve(), self.upload_dir):
            try:
                marker.unlink(missing_ok=True)
            except OSError:
                pass

    def _is_safe_pending_path(self, pending_path: Path) -> bool:
        pending_dir = self._pending_delete_directory()
        try:
            resolved = pending_path.resolve()
        except OSError:
            return False
        return (
            _is_relative_to(pending_dir, self.upload_dir)
            and _is_relative_to(resolved, pending_dir)
            and resolved.parent == pending_dir
        )

    def _reconcile_pending_deletes(self) -> None:
        """Recover crash-interrupted upload deletion without following untrusted paths."""

        pending_dir = self._pending_delete_directory()
        if not _is_relative_to(pending_dir, self.upload_dir) or not pending_dir.is_dir():
            return
        try:
            with self._index_guard():
                data = self._load_unlocked()
                referenced_paths = {
                    str(Path(str(document.get("path", ""))).resolve())
                    for document in data["documents"]
                    if document.get("source_type") == "upload"
                    and document.get("path")
                    and _is_relative_to(Path(str(document["path"])).resolve(), self.upload_dir)
                }
                for marker in pending_dir.glob("*.marker.json"):
                    self._reconcile_pending_marker(marker, referenced_paths)
        except (IndexRecoveryError, OSError, TimeoutError):
            return

    def _reconcile_pending_marker(self, marker: Path, referenced_paths: set[str]) -> None:
        if marker.parent.resolve() != self._pending_delete_directory() or not _is_relative_to(marker.resolve(), self.upload_dir):
            return
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(payload, Mapping):
            return
        try:
            pending = Path(str(payload.get("pending_path", ""))).resolve()
            original = Path(str(payload.get("original_path", ""))).resolve()
        except OSError:
            return
        if not self._is_safe_pending_path(pending) or not _is_relative_to(original, self.upload_dir):
            return
        if str(original) in referenced_paths:
            try:
                if pending.exists():
                    if original.exists():
                        pending.unlink()
                    else:
                        pending.replace(original)
                marker.unlink(missing_ok=True)
            except OSError:
                return
            return
        try:
            pending.unlink(missing_ok=True)
            marker.unlink(missing_ok=True)
        except OSError:
            return


def _read_index(path: Path) -> dict[str, list[dict[str, Any]]] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return _normalise_index(parsed)


def _normalise_index(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "documents": _mapping_items(data.get("documents")),
        "chunks": _mapping_items(data.get("chunks")),
    }


def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".knowledge-", suffix=".tmp", delete=False) as temporary:
            json.dump(data, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _mapping_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _same_resolved_path(document: Mapping[str, Any], path: Path) -> bool:
    stored_path = document.get("path")
    if not stored_path:
        return False
    try:
        return Path(str(stored_path)).expanduser().resolve() == path.resolve()
    except OSError:
        return False


def _find_document(documents: list[dict[str, Any]], expected: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if expected is None:
        return None
    expected_id = expected.get("document_id")
    expected_path = Path(str(expected.get("path", ""))).resolve()
    return next(
        (
            item for item in documents
            if item.get("document_id") == expected_id and _same_resolved_path(item, expected_path)
        ),
        None,
    )


def _matching_document_ids(documents: list[dict[str, Any]], document: Mapping[str, Any]) -> set[str]:
    target = Path(str(document["path"])).resolve()
    return {
        str(item["document_id"])
        for item in documents
        if item.get("document_id") is not None
        and (item.get("document_id") == document.get("document_id") or _same_resolved_path(item, target))
    }


def _document_version(document: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        document.get("document_id"),
        str(Path(str(document.get("path", ""))).resolve()),
        document.get("source_type"),
        document.get("stored_name"),
        document.get("sha256"),
        document.get("size_bytes"),
        document.get("modified_at"),
    )


def _file_state(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def _index_recovery_result(operation: str) -> dict[str, Any]:
    return {operation: False, "error": True, "reason": "index_recovery_failed"}


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
    seen, sources = set(), []
    for item in results:
        key = item.get("document_id")
        if key in seen:
            continue
        seen.add(key)
        sources.append({"document_id": key, "name": item.get("document_name"), "path": item.get("path")})
    return sources


def _document_id(path: Path) -> str:
    import hashlib

    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
