import os
import re
from pathlib import Path


INVALID_FILENAME_CHARS = r'[<>:"/\\|?*]'
DEFAULT_FILE_SEARCH_ALLOWED_DIRS = "workspace/exports"
WINDOWS_SYSTEM_DIR_NAMES = {"windows", "program files", "program files (x86)"}


def get_workspace_dir() -> Path:
    return Path(os.getenv("WORKSPACE_DIR", "workspace")).resolve()


def get_export_dir() -> Path:
    return Path(os.getenv("EXPORT_DIR", str(get_workspace_dir() / "exports"))).resolve()


def get_allowed_search_dirs() -> list[Path]:
    configured = os.getenv("FILE_SEARCH_ALLOWED_DIRS", DEFAULT_FILE_SEARCH_ALLOWED_DIRS)
    allowed_dirs: list[Path] = []
    for raw_part in configured.split(";"):
        raw_part = raw_part.strip()
        if not raw_part:
            continue
        path = Path(os.path.expandvars(raw_part)).expanduser().resolve()
        if _is_windows_root(path) or _is_windows_system_path(path):
            continue
        allowed_dirs.append(path)
    return allowed_dirs


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


def is_path_inside_allowed_dirs(path: str | Path) -> bool:
    try:
        resolved = Path(path).resolve()
        return any(_is_relative_to(resolved, allowed_dir) for allowed_dir in get_allowed_search_dirs())
    except OSError:
        return False


def normalize_user_path(path: str) -> Path:
    if ".." in Path(path).parts:
        raise ValueError("Ungueltiger Pfad: '..' ist nicht erlaubt.")
    resolved = Path(os.path.expandvars(path)).expanduser().resolve()
    if _is_windows_root(resolved) or _is_windows_system_path(resolved):
        raise ValueError("Ungueltiger Pfad: Systemverzeichnisse sind nicht erlaubt.")
    if not is_path_inside_allowed_dirs(resolved):
        raise ValueError("Datei liegt ausserhalb der erlaubten Verzeichnisse.")
    return resolved


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


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _is_windows_root(path: Path) -> bool:
    anchor = path.anchor
    return bool(anchor) and str(path).lower() == anchor.lower()


def _is_windows_system_path(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    return any(part in WINDOWS_SYSTEM_DIR_NAMES for part in parts)
