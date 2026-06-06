import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.tools.files.path_safety import get_allowed_search_dirs, get_export_dir


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
        matches: list[Path] = []

        if cleaned_query:
            for directory in get_allowed_search_dirs():
                if not directory.exists() or not directory.is_dir():
                    continue
                for path in _iter_supported_files(directory):
                    if len(matches) >= max_results:
                        break
                    if allowed_extensions and path.suffix.lower() not in allowed_extensions:
                        continue
                    searchable = f"{path.name} {path}".lower()
                    if cleaned_query in searchable:
                        matches.append(path)
                if len(matches) >= max_results:
                    break

        files = [_file_result(path) for path in matches[:max_results]]
        return {
            "query": query,
            "count": len(files),
            "files": files,
            "message": f"{len(files)} Dateien gefunden.",
        }

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
    allowed_dirs = get_allowed_search_dirs()
    onedrive_env = os.getenv("OneDrive") or os.getenv("ONEDRIVE") or ""
    onedrive_path = Path(onedrive_env).resolve() if onedrive_env else None
    return {
        "enabled": os.getenv("FILE_SEARCH_ENABLED", "true").strip().lower() == "true",
        "allowed_dirs": [str(path) for path in allowed_dirs],
        "onedrive_env": str(onedrive_path) if onedrive_path else None,
        "onedrive_configured": _is_onedrive_configured(onedrive_path, allowed_dirs),
        "max_results": int(os.getenv("FILE_SEARCH_MAX_RESULTS", "25")),
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


def _iter_supported_files(directory: Path) -> list[Path]:
    files: list[Path] = []
    for root, _dirs, names in os.walk(directory):
        for name in names:
            path = Path(root) / name
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(path)
    files.sort(key=lambda path: (path.name.lower(), str(path).lower()))
    return files


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
