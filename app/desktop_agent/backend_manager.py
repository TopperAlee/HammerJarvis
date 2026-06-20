from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

from app.desktop_agent.config import DesktopAgentConfig
from app.desktop_agent.python_runtime import preflight_python_runtime, resolve_project_python


CREATE_NO_WINDOW = 0x08000000


class BackendManager:
    def __init__(self, config: DesktopAgentConfig) -> None:
        self.config = config
        self.started_process: subprocess.Popen[Any] | None = None
        self.backend_python: Path | None = None
        self.backend_pid: int | None = None
        self.websocket_transport: str = ""
        self.last_preflight: dict[str, Any] = {}

    def is_backend_ready(self) -> bool:
        preflight = self.preflight()
        if not preflight.get("ok"):
            self.last_preflight = preflight
            return False
        try:
            response = requests.get(self.config.health_url, timeout=2)
            return response.status_code == 200 and response.json().get("status") == "ready"
        except Exception:
            return False

    def ensure_backend(self) -> dict[str, Any]:
        preflight = self.preflight()
        self.last_preflight = preflight
        if not preflight.get("ok"):
            return {"ready": False, "started": False, "code": preflight.get("code"), "message": preflight.get("message"), "preflight": preflight}
        if self.is_backend_ready():
            return {
                "ready": True,
                "started": False,
                "message": "Backend ist bereits erreichbar.",
                "backend_python": str(self.backend_python or ""),
                "websocket_transport": self.websocket_transport,
            }
        if not self.config.start_backend:
            return {"ready": False, "started": False, "message": "Backend ist nicht erreichbar und Autostart ist deaktiviert."}
        self.start_backend()
        deadline = time.monotonic() + self.config.backend_timeout_seconds
        while time.monotonic() < deadline:
            if self.is_backend_ready():
                return {
                    "ready": True,
                    "started": True,
                    "message": "Backend wurde gestartet.",
                    "backend_python": str(self.backend_python or ""),
                    "backend_pid": self.backend_pid,
                    "websocket_transport": self.websocket_transport,
                }
            time.sleep(0.5)
        return {"ready": False, "started": True, "message": "Backendstart hat das Timeout erreicht."}

    def start_backend(self) -> None:
        if self.started_process and self.started_process.poll() is None:
            return
        python = self._pythonw_path()
        args = [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"]
        startupinfo = None
        creationflags = 0
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = CREATE_NO_WINDOW
        self.started_process = subprocess.Popen(
            args,
            cwd=str(self.config.project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        self.backend_pid = self.started_process.pid

    def stop_started_backend(self) -> None:
        if self.started_process and self.started_process.poll() is None:
            self.started_process.terminate()
        self.started_process = None

    def preflight(self) -> dict[str, Any]:
        try:
            python = self._pythonw_path()
        except RuntimeError as exc:
            return {"ok": False, "code": "project_venv_missing", "message": str(exc)}
        result = preflight_python_runtime(python, self.config.project_root)
        if result.get("ok"):
            self.websocket_transport = str(result.get("websocket_transport") or "")
        return result

    def _pythonw_path(self) -> Path:
        runtime = resolve_project_python(self.config.project_root)
        self.backend_python = runtime.executable
        return runtime.executable
