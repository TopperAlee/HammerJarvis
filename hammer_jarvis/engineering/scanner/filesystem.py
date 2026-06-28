import os
from dataclasses import dataclass, field
from pathlib import Path

from app.tools.files.path_safety import normalize_user_path


IGNORED_DIR_NAMES = {".git", ".venv", "venv", "__pycache__", "node_modules"}
ALLOWED_EXTENSIONS = {".csv", ".txt", ".xml", ".json", ".md"}


@dataclass
class ScannedProjectFile:
    path: Path
    relative_path: str
    extension: str


@dataclass
class ProjectScanResult:
    root_path: Path
    files: list[ScannedProjectFile] = field(default_factory=list)
    skipped_dirs: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    max_files_reached: bool = False


class ProjectScanner:
    def __init__(self, max_depth: int = 8, max_files: int = 500) -> None:
        self.max_depth = max_depth
        self.max_files = max_files

    def scan(self, root_path: str | Path) -> ProjectScanResult:
        root = normalize_user_path(str(root_path))
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Engineering-Projektordner nicht gefunden: {root}")

        result = ProjectScanResult(root_path=root)
        for current_root, dirs, names in os.walk(root):
            current_path = Path(current_root)
            depth = _relative_depth(root, current_path)
            original_dirs = list(dirs)
            dirs[:] = [
                directory
                for directory in dirs
                if directory.lower() not in IGNORED_DIR_NAMES and depth < self.max_depth
            ]
            for directory in original_dirs:
                if directory not in dirs:
                    result.skipped_dirs.append(str(current_path / directory))

            for name in sorted(names, key=str.lower):
                path = current_path / name
                extension = path.suffix.lower()
                if extension not in ALLOWED_EXTENSIONS:
                    result.skipped_files.append(str(path))
                    continue
                result.files.append(
                    ScannedProjectFile(
                        path=path,
                        relative_path=path.relative_to(root).as_posix(),
                        extension=extension,
                    )
                )
                if len(result.files) >= self.max_files:
                    result.max_files_reached = True
                    dirs[:] = []
                    break
            if result.max_files_reached:
                break
        return result


def _relative_depth(base: Path, path: Path) -> int:
    try:
        return len(path.relative_to(base).parts)
    except ValueError:
        return 0

