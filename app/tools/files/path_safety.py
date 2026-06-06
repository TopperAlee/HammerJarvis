import os
import re
from pathlib import Path


INVALID_FILENAME_CHARS = r'[<>:"/\\|?*]'


def get_workspace_dir() -> Path:
    return Path(os.getenv("WORKSPACE_DIR", "workspace")).resolve()


def get_export_dir() -> Path:
    return Path(os.getenv("EXPORT_DIR", str(get_workspace_dir() / "exports"))).resolve()


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(INVALID_FILENAME_CHARS, "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip(" ._")
    return cleaned or "export"


def safe_join(base_dir: str | Path, filename: str) -> Path:
    raw = Path(filename)
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("ungueltiger Dateiname: Pfade und '..' sind nicht erlaubt.")
    base = Path(base_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    candidate = (base / sanitize_filename(filename)).resolve()
    if not ensure_allowed_path(str(candidate)):
        raise ValueError("Ungueltiger Dateipfad: ausserhalb des Export-Verzeichnisses.")
    return _deduplicate(candidate)


def ensure_allowed_path(path: str) -> bool:
    try:
        resolved = Path(path).resolve()
        export_dir = get_export_dir()
        resolved.relative_to(export_dir)
    except ValueError:
        return False
    return True


def _deduplicate(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(1, 1000):
        candidate = parent / f"{stem}_{index:03d}{suffix}"
        if not candidate.exists():
            return candidate
    raise ValueError("Kein freier Dateiname im Export-Verzeichnis gefunden.")
