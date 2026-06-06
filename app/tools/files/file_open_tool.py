import os
from pathlib import Path
from typing import Any

from app.tools.files.file_search_tool import FileSearchTool
from app.tools.files.path_safety import normalize_user_path


class FileOpenTool:
    def open_file(self, path: str) -> dict[str, Any]:
        try:
            resolved = normalize_user_path(path)
        except ValueError:
            return {
                "opened": False,
                "blocked": True,
                "message": "Datei liegt ausserhalb der erlaubten Verzeichnisse.",
            }
        if not resolved.exists() or not resolved.is_file():
            return {
                "opened": False,
                "blocked": False,
                "path": str(resolved),
                "message": "Datei wurde nicht gefunden.",
            }
        try:
            os.startfile(str(resolved))
        except Exception:
            return {
                "opened": False,
                "blocked": False,
                "path": str(resolved),
                "message": "Datei konnte nicht geoeffnet werden.",
            }
        return {
            "opened": True,
            "path": str(resolved),
            "message": f"Datei wurde geoeffnet: {resolved}",
        }

    def open_latest_export(self) -> dict[str, Any]:
        recent = FileSearchTool().list_recent_exports(limit=1)
        files = recent.get("files", [])
        if not files:
            return {
                "opened": False,
                "blocked": False,
                "message": "Keine exportierte Datei gefunden.",
            }
        return self.open_file(str(files[0]["path"]))


def open_search_result_if_single(query: str, extension: str | None = None) -> dict[str, Any]:
    extensions = [extension] if extension else None
    result = FileSearchTool().search_files(query=query, extensions=extensions, limit=5)
    files = result.get("files", [])
    if len(files) == 1:
        return FileOpenTool().open_file(str(files[0]["path"]))
    return {
        "opened": False,
        "blocked": False,
        "matches": files,
        "message": (
            "Ich habe mehrere passende Dateien gefunden. Bitte sag mir, welche ich oeffnen soll."
            if files
            else "Ich habe keine passende Datei gefunden."
        ),
    }
