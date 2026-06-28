"""Safe local storage paths and file helpers for the knowledge index."""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


SUPPORTED_KNOWLEDGE_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".xlsm",
    ".csv",
    ".txt",
    ".md",
    ".json",
}
_INVALID_WINDOWS_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class KnowledgeStoragePaths:
    """Resolved, local-only paths used by the knowledge store."""

    root: Path
    index_file: Path
    upload_dir: Path

    @property
    def backup_file(self) -> Path:
        return self.index_file.with_suffix(self.index_file.suffix + ".bak")

    @property
    def lock_file(self) -> Path:
        return self.index_file.with_suffix(self.index_file.suffix + ".lock")


def knowledge_storage_paths() -> KnowledgeStoragePaths:
    local_app_data = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    root = (local_app_data / "HammerJarvis" / "knowledge").resolve()
    index_file = Path(os.getenv("KNOWLEDGE_STORE_FILE") or (root / "knowledge_index.json")).expanduser().resolve()
    upload_dir = Path(os.getenv("KNOWLEDGE_UPLOAD_DIR") or (root / "uploads")).expanduser().resolve()
    return KnowledgeStoragePaths(root=root, index_file=index_file, upload_dir=upload_dir)


def validate_upload_filename(filename: str) -> tuple[bool, str | None, str | None]:
    """Validate user supplied names before they ever become a filesystem path."""

    name = str(filename or "").strip()
    if not name or name in {".", ".."}:
        return False, None, "invalid_filename"
    candidate = Path(name)
    if candidate.is_absolute() or len(candidate.parts) != 1 or ".." in candidate.parts:
        return False, None, "invalid_filename"
    if _INVALID_WINDOWS_FILENAME.search(name) or name.endswith((".", " ")):
        return False, None, "invalid_filename"
    extension = candidate.suffix.lower()
    if extension not in SUPPORTED_KNOWLEDGE_EXTENSIONS:
        return False, None, "unsupported_file_type"
    return True, name, None


def safe_stored_name(extension: str) -> str:
    """Generate a filesystem-only name; the original filename stays metadata."""

    return f"{uuid4().hex}{extension.lower()}"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def max_upload_bytes() -> int:
    try:
        megabytes = float(os.getenv("KNOWLEDGE_MAX_UPLOAD_MB", "25"))
    except ValueError:
        megabytes = 25
    return max(1, int(megabytes * 1024 * 1024))


class CrossProcessFileLock:
    """Advisory lock for one local JSON index, including Windows processes."""

    def __init__(self, path: Path, timeout_seconds: float = 30) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self._stream = None

    def __enter__(self) -> "CrossProcessFileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("a+b")
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                # ``msvcrt.locking`` needs one existing byte.  Initialising it
                # can race with a process that has already locked that byte, so
                # handle it as ordinary lock contention and retry below.
                self._stream.seek(0, os.SEEK_END)
                if self._stream.tell() == 0:
                    self._stream.write(b"0")
                    self._stream.flush()
                self._stream.seek(0)
                self._acquire_once()
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    self._stream.close()
                    self._stream = None
                    raise TimeoutError("knowledge_index_lock_timeout")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._stream is None:
            return
        try:
            self._release()
        finally:
            self._stream.close()
            self._stream = None

    def _acquire_once(self) -> None:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._stream.fileno(), msvcrt.LK_NBLCK, 1)
            return
        import fcntl

        fcntl.flock(self._stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release(self) -> None:
        if os.name == "nt":
            import msvcrt

            self._stream.seek(0)
            msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
