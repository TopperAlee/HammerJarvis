import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.tools.files.content_extractors import SUPPORTED_CONTENT_EXTENSIONS, extract_text
from app.tools.files.path_safety import get_allowed_search_dirs, normalize_user_path


class ContentSearchTool:
    def search_file_contents(
        self,
        query: str,
        extensions: list[str] | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        normalized_extensions = _normalize_extensions(extensions)
        matches: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        searched_dirs: list[str] = []
        for directory in get_allowed_search_dirs():
            if not directory.exists() or not directory.is_dir():
                skipped.append({"path": str(directory), "reason": "Verzeichnis fehlt"})
                continue
            searched_dirs.append(str(directory))
            for path in _iter_content_files(directory, normalized_extensions):
                file_result = _inspect_allowed_path(path, query)
                if file_result.get("skipped") or file_result.get("error"):
                    skipped.append({"path": str(path), "reason": str(file_result.get("reason") or file_result.get("message") or "Fehler")})
                    continue
                if file_result.get("score", 0) > 0:
                    matches.append(file_result)
        matches.sort(key=lambda item: item["score"], reverse=True)
        limited = matches[:limit]
        result = {
            "query": query,
            "extensions": sorted(normalized_extensions) if normalized_extensions else [],
            "count": len(limited),
            "files": limited,
            "searched_dirs": searched_dirs,
            "skipped": skipped,
            "skipped_count": len(skipped),
            "message": _content_search_message(len(limited), skipped, normalized_extensions),
        }
        from app.assistant.session_state import session_state

        session_state.save_content_results(result)
        return result

    def inspect_file(self, path: str, query: str | None = None) -> dict[str, Any]:
        try:
            resolved = normalize_user_path(path)
        except ValueError:
            return {"blocked": True, "path": path, "message": "Datei liegt ausserhalb der erlaubten Verzeichnisse."}
        if not resolved.exists() or not resolved.is_file():
            return {"blocked": False, "path": str(resolved), "error": True, "message": "Datei wurde nicht gefunden."}
        return _inspect_allowed_path(resolved, query or "")


def _inspect_allowed_path(path: Path, query: str) -> dict[str, Any]:
    extracted = extract_text(path)
    if extracted.get("skipped") or extracted.get("error"):
        return {**extracted, "name": path.name}
    text = str(extracted.get("text") or "")
    lowered_query = query.lower()
    lowered_name = path.name.lower()
    lowered_path = str(path).lower()
    lowered_text = text.lower()
    match_sources: list[str] = []
    score = 0
    if lowered_query and lowered_query in lowered_name:
        score += 100
        match_sources.append("filename")
    match_count = lowered_text.count(lowered_query) if lowered_query else 0
    if match_count:
        score += 50 + min(match_count, 10)
        match_sources.append("content")
    if lowered_query and lowered_query in lowered_path and "filename" not in match_sources:
        score += 10
        match_sources.append("path")
    score += _recent_bonus(path)
    return {
        "name": path.name,
        "path": str(path),
        "extension": path.suffix.lower(),
        "score": score,
        "match_sources": match_sources,
        "matched": bool(match_sources),
        "match_count": match_count,
        "snippets": _snippets(text, query),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "preview": str(extracted.get("preview") or ""),
    }


def _iter_content_files(directory: Path, extensions: set[str]) -> list[Path]:
    files: list[Path] = []
    for root, _dirs, names in os.walk(directory):
        for name in names:
            path = Path(root) / name
            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_CONTENT_EXTENSIONS:
                continue
            if extensions and suffix not in extensions:
                continue
            files.append(path)
    return files


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
        if value in SUPPORTED_CONTENT_EXTENSIONS:
            normalized.add(value)
    return normalized


def _snippets(text: str, query: str) -> list[str]:
    if not query:
        return []
    snippets: list[str] = []
    for match in re.finditer(re.escape(query), text, flags=re.I):
        start = max(match.start() - 60, 0)
        end = min(match.end() + 60, len(text))
        snippets.append(" ".join(text[start:end].split()))
        if len(snippets) >= 3:
            break
    return snippets


def _recent_bonus(path: Path) -> int:
    age_days = max((datetime.now().timestamp() - path.stat().st_mtime) / 86400, 0)
    return max(0, 5 - int(age_days))


def _content_search_message(count: int, skipped: list[dict[str, str]], extensions: set[str]) -> str:
    if count == 0 and skipped and (not extensions or ".pdf" in extensions):
        return (
            "Ich konnte keine passenden Inhalte finden. Einige PDF-Dateien konnten nicht gelesen werden, "
            "vermutlich weil sie beschädigt, keine echten PDFs oder OneDrive-Platzhalter sind."
        )
    return f"{count} Dateien mit Inhaltstreffern gefunden."
