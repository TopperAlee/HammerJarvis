from __future__ import annotations

import subprocess
import sys
from typing import Any

from app.desktop_agent.config import DesktopAgentConfig


class LocalSpeech:
    def __init__(self, config: DesktopAgentConfig) -> None:
        self.config = config
        self.spoken_ready = False

    def speak_ready_once(self) -> dict[str, Any]:
        if self.spoken_ready or not self.config.ready_announcement:
            return {"attempted": False, "success": None, "error": None}
        self.spoken_ready = True
        return self.speak(self.config.ready_text)

    def speak(self, text: str) -> dict[str, Any]:
        script = self.config.project_root / "scripts" / "speak-local.ps1"
        if not script.exists():
            return {"attempted": True, "success": False, "error": "speak_script_missing"}
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script.resolve()),
                    "-Text",
                    text,
                ],
                cwd=str(self.config.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
                creationflags=0x08000000 if sys.platform.startswith("win") else 0,
            )
            error = _safe_error(result.stderr) if result.returncode else None
            return {"attempted": True, "success": result.returncode == 0, "error": error, "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            return {"attempted": True, "success": False, "error": "speech_timeout"}
        except Exception as exc:
            return {"attempted": True, "success": False, "error": exc.__class__.__name__}


def _safe_error(text: str | None) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[:300] or "speech_failed"
