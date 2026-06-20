from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PythonRuntime:
    executable: Path
    source: str


def resolve_project_python(project_root: Path) -> PythonRuntime:
    configured = os.getenv("DESKTOP_AGENT_PYTHON_EXECUTABLE", "").strip()
    if configured:
        path = Path(configured)
        if path.exists():
            return PythonRuntime(path, "DESKTOP_AGENT_PYTHON_EXECUTABLE")
        raise RuntimeError(f"project_venv_missing: konfigurierter Python-Interpreter existiert nicht: {path}")

    scripts_dir = project_root / ".venv" / "Scripts"
    pythonw = scripts_dir / "pythonw.exe"
    python = scripts_dir / "python.exe"
    if pythonw.exists():
        return PythonRuntime(pythonw, "project_venv_pythonw")
    if python.exists():
        return PythonRuntime(python, "project_venv_python")
    raise RuntimeError(
        "project_venv_missing: Projekt-venv nicht gefunden. "
        "Bitte im Projektverzeichnis ausfuehren: python -m venv .venv; .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    )


def current_agent_python(project_root: Path) -> PythonRuntime:
    resolved = resolve_project_python(project_root)
    current = Path(sys.executable)
    if _same_file(current, resolved.executable) or _same_project_venv_python(current, resolved.executable):
        return PythonRuntime(current, "current_project_python")
    raise RuntimeError(
        f"project_venv_mismatch: Desktop-Agent laeuft mit {current}, erwartet aber {resolved.executable}. "
        "Starte den Agenten ueber scripts\\start-desktop-agent.ps1 oder installiere die geplante Aufgabe neu."
    )


def preflight_python_runtime(python: Path, project_root: Path) -> dict[str, Any]:
    preflight_python = _preflight_executable(python)
    script = (
        "import importlib.util, json, sys\n"
        "checks = {name: importlib.util.find_spec(name) is not None for name in ['fastapi', 'uvicorn', 'websockets', 'wsproto']}\n"
        "transport = 'websockets' if checks['websockets'] else ('wsproto' if checks['wsproto'] else '')\n"
        "print(json.dumps({'python': sys.executable, 'checks': checks, 'websocket_transport': transport}))\n"
    )
    try:
        result = subprocess.run(
            [str(preflight_python), "-c", script],
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "code": "python_preflight_failed", "message": f"Python-Preflight fehlgeschlagen: {exc.__class__.__name__}"}
    if result.returncode != 0:
        return {"ok": False, "code": "python_preflight_failed", "message": "Python-Preflight konnte nicht ausgefuehrt werden."}
    try:
        import json

        payload = json.loads(result.stdout.strip())
    except Exception:
        return {"ok": False, "code": "python_preflight_failed", "message": "Python-Preflight lieferte ungueltige Ausgabe."}
    checks = payload.get("checks") or {}
    if not checks.get("fastapi"):
        return {"ok": False, "code": "fastapi_missing", "message": "FastAPI fehlt in der Projekt-venv. Bitte requirements.txt lokal installieren."}
    if not checks.get("uvicorn"):
        return {"ok": False, "code": "uvicorn_missing", "message": "Uvicorn fehlt in der Projekt-venv. Bitte requirements.txt lokal installieren."}
    if not payload.get("websocket_transport"):
        return {
            "ok": False,
            "code": "websocket_transport_missing",
            "message": "WebSocket-Transport fehlt. Bitte lokal installieren: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt",
        }
    return {"ok": True, "python": payload.get("python"), "websocket_transport": payload.get("websocket_transport"), "checks": checks}


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.resolve().samefile(right.resolve())
    except OSError:
        return str(left.resolve()).casefold() == str(right.resolve()).casefold()


def _preflight_executable(python: Path) -> Path:
    if python.name.lower() == "pythonw.exe":
        console_python = python.with_name("python.exe")
        if console_python.exists():
            return console_python
    return python


def _same_project_venv_python(current: Path, resolved: Path) -> bool:
    current_resolved = current.resolve()
    expected = resolved.resolve()
    if current_resolved.parent != expected.parent:
        return False
    names = {current_resolved.name.lower(), expected.name.lower()}
    return names <= {"python.exe", "pythonw.exe"}
