import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.tools.files.path_safety import DEFAULT_FILE_SEARCH_ALLOWED_DIRS, get_allowed_search_dirs, get_export_dir
from app.assistant.performance.timing import time_operation


SUPPORTED_EXTENSIONS = {
    ".xlsx",
    ".xls",
    ".csv",
    ".docx",
    ".pdf",
    ".txt",
    ".md",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
}
SKIP_DIR_NAMES = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "appdata"}


class FileSearchTool:
    def search_files(
        self,
        query: str,
        extensions: list[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        cleaned_query = query.strip().lower()
        max_results = limit or int(os.getenv("FILE_SEARCH_MAX_RESULTS", "25"))
        allowed_extensions = _normalize_extensions(extensions)
        matches: list[dict[str, Any]] = []
        searched_dirs: list[str] = []
        skipped_dirs: list[str] = []

        with time_operation("file_search.search_files", "file_search"):
            deadline = time.monotonic() + float(os.getenv("FILE_SEARCH_TIMEOUT_SECONDS", "20"))
            if cleaned_query:
                for directory in get_allowed_search_dirs():
                    if not directory.exists() or not directory.is_dir():
                        skipped_dirs.append(str(directory))
                        continue
                    searched_dirs.append(str(directory))
                    for path in _iter_supported_files(directory, skipped_dirs, deadline):
                        if len(matches) >= max_results or time.monotonic() > deadline:
                            break
                        if allowed_extensions and path.suffix.lower() not in allowed_extensions:
                            continue
                        file_match = _path_match_result(path, cleaned_query)
                        if file_match:
                            matches.append(file_match)
                    if len(matches) >= max_results or time.monotonic() > deadline:
                        break

        matches.sort(key=lambda item: item["score"], reverse=True)
        files = matches[:max_results]
        normalized_extensions = sorted(allowed_extensions)
        result = {
            "query": query,
            "extensions": normalized_extensions,
            "searched_dirs": searched_dirs,
            "skipped_dirs": skipped_dirs,
            "count": len(files),
            "files": files,
            "message": _search_message(files),
            "duration_limited": time.monotonic() > deadline if cleaned_query else False,
        }
        from app.assistant.session_state import session_state

        session_state.save_file_results(result)
        return result

    def list_recent_exports(self, limit: int = 10) -> dict[str, Any]:
        export_dir = get_export_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        files = [
            path
            for path in export_dir.iterdir()
            if path.is_file() and path.name != ".gitkeep" and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        limited = files[:limit]
        return {
            "count": len(limited),
            "files": [_file_result(path) for path in limited],
            "message": f"{len(limited)} Dateien gefunden.",
        }

    def find_by_name(self, query: str, limit: int = 25) -> dict[str, Any]:
        return self.search_files(query=query, limit=limit)


def get_file_search_status() -> dict[str, Any]:
    raw = os.getenv("FILE_SEARCH_ALLOWED_DIRS", DEFAULT_FILE_SEARCH_ALLOWED_DIRS)
    allowed_dirs = get_allowed_search_dirs()
    existing_dirs = [path for path in allowed_dirs if path.exists() and path.is_dir()]
    missing_dirs = [path for path in allowed_dirs if not path.exists() or not path.is_dir()]
    onedrive_env = os.getenv("OneDrive") or os.getenv("ONEDRIVE") or ""
    onedrive_path = Path(onedrive_env).resolve() if onedrive_env else None
    return {
        "enabled": os.getenv("FILE_SEARCH_ENABLED", "true").strip().lower() == "true",
        "allowed_dirs_raw": raw,
        "allowed_dirs": [str(path) for path in allowed_dirs],
        "resolved_allowed_dirs": [str(path) for path in allowed_dirs],
        "existing_allowed_dirs": [str(path) for path in existing_dirs],
        "missing_allowed_dirs": [str(path) for path in missing_dirs],
        "onedrive_env": str(onedrive_path) if onedrive_path else None,
        "onedrive_configured": _is_onedrive_configured(onedrive_path, allowed_dirs),
        "max_results": int(os.getenv("FILE_SEARCH_MAX_RESULTS", "25")),
        "max_depth": int(os.getenv("FILE_SEARCH_MAX_DEPTH", "12")),
        "timeout_seconds": float(os.getenv("FILE_SEARCH_TIMEOUT_SECONDS", "20")),
    }


def _normalize_extensions(extensions: list[str] | None) -> set[str]:
    if not extensions:
        return set()
    normalized: set[str] = set()
    for extension in extensions:
        value = extension.strip().lower()
        if not value:
            continue
        if not value.startswith("."):
            value = f".{value}"
        if value in SUPPORTED_EXTENSIONS:
            normalized.add(value)
    return normalized


def _search_message(files: list[dict[str, Any]]) -> str:
    if not files:
        return (
            "Ich habe in den erlaubten Ordnern gesucht, aber keine passende Datei gefunden. "
            "Aktuell suche ich nur in Dateiname und Pfad, nicht im Dateiinhalt."
        )
    if all(file.get("path_match_only") for file in files):
        return (
            "Ich habe viele Treffer gefunden, weil der Ordnerpfad den Suchbegriff enthält. "
            "Für genauere Ergebnisse nutze die Inhaltssuche."
        )
    return f"{len(files)} Dateien gefunden."


def _iter_supported_files(directory: Path, skipped_dirs: list[str] | None = None, deadline: float | None = None) -> list[Path]:
    files: list[Path] = []
    for root, _dirs, names in os.walk(directory):
        if deadline is not None and time.monotonic() > deadline:
            break
        root_path = Path(root)
        depth = _relative_depth(directory, root_path)
        original_dirs = list(_dirs)
        _dirs[:] = [
            name
            for name in _dirs
            if depth < int(os.getenv("FILE_SEARCH_MAX_DEPTH", "12"))
            and name.lower() not in SKIP_DIR_NAMES
            and not name.startswith(".")
        ]
        if skipped_dirs is not None:
            for name in original_dirs:
                if name not in _dirs:
                    skipped_dirs.append(str(root_path / name))
        for name in names:
            path = Path(root) / name
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(path)
    files.sort(key=lambda path: (path.name.lower(), str(path).lower()))
    return files


def _relative_depth(base: Path, path: Path) -> int:
    try:
        return len(path.relative_to(base).parts)
    except ValueError:
        return 0


def _file_result(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "source": "workspace_exports" if _is_export_file(path) else "allowed_dir",
    }


def _path_match_result(path: Path, cleaned_query: str) -> dict[str, Any] | None:
    lowered_name = path.name.lower()
    lowered_path = str(path).lower()
    match_sources: list[str] = []
    score = 0
    if cleaned_query in lowered_name:
        match_sources.append("filename")
        score += 100
    if cleaned_query in lowered_path:
        match_sources.append("path")
        if "filename" not in match_sources:
            score += 10
    if not match_sources:
        return None
    result = _file_result(path)
    result["score"] = score
    result["match_sources"] = match_sources
    result["path_match_only"] = match_sources == ["path"]
    return result


def _is_export_file(path: Path) -> bool:
    try:
        path.resolve().relative_to(get_export_dir())
        return True
    except ValueError:
        return False


def _is_onedrive_configured(onedrive_path: Path | None, allowed_dirs: list[Path]) -> bool:
    if onedrive_path is None:
        return False
    for allowed_dir in allowed_dirs:
        try:
            onedrive_path.relative_to(allowed_dir)
            return True
        except ValueError:
            pass
        try:
            allowed_dir.relative_to(onedrive_path)
            return True
        except ValueError:
            pass
    return False
