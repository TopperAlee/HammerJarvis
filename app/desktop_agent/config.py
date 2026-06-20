from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from app.desktop_agent.wake_configuration import DEFAULT_ACCEPTED_TRANSCRIPTS, clean_accepted_transcripts


DEFAULT_WAKE_WORD = "Jarvis"


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _list_env(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    value = os.getenv(name)
    if not value:
        return default
    items: list[int] = []
    for part in value.split(","):
        try:
            items.append(max(250, min(30000, int(part.strip()))))
        except ValueError:
            continue
    return tuple(items) or default


@dataclass(frozen=True)
class DesktopAgentConfig:
    enabled: bool = False
    start_backend: bool = True
    open_browser_on_wake: bool = True
    dashboard_url: str = "http://127.0.0.1:8001/dashboard"
    backend_url: str = "http://127.0.0.1:8001"
    backend_timeout_seconds: int = 30
    dashboard_timeout_seconds: int = 10
    ready_announcement: bool = True
    ready_text: str = "Alle Systeme online und bereit"
    wake_engine: str = "windows_speech"
    wake_word: str = DEFAULT_WAKE_WORD
    wake_confidence_threshold: float = 0.40
    wake_cooldown_ms: int = 3500
    wake_listener_ready_timeout_seconds: int = 15
    wake_listener_restart_delays_seconds: tuple[int, ...] = (1, 3, 10)
    wake_recognizer_culture: str = "auto"
    wake_accepted_transcripts: tuple[str, ...] = DEFAULT_ACCEPTED_TRANSCRIPTS
    wake_word_model_path: Path = Path("app/data/models/wake/jarvis.onnx")
    command_recognition_timeout_ms: int = 9000
    desktop_event_reconnect_delays_ms: tuple[int, ...] = (1000, 2000, 5000)
    agent_python: str = ""
    backend_python: str = ""
    websocket_transport: str = ""
    project_root: Path = Path.cwd()

    @property
    def health_url(self) -> str:
        return f"{self.backend_url.rstrip('/')}/assistant/health"

    @property
    def desktop_status_url(self) -> str:
        return f"{self.backend_url.rstrip('/')}/assistant/desktop/status"

    @property
    def desktop_wake_url(self) -> str:
        return f"{self.backend_url.rstrip('/')}/assistant/desktop/wake"

    @property
    def desktop_heartbeat_url(self) -> str:
        return f"{self.backend_url.rstrip('/')}/assistant/desktop/agent-heartbeat"


def load_desktop_agent_config(project_root: Path | None = None) -> DesktopAgentConfig:
    root = project_root or Path.cwd()
    load_dotenv(root / ".env")
    dashboard_url = os.getenv("DESKTOP_AGENT_DASHBOARD_URL", "http://127.0.0.1:8001/dashboard").strip()
    backend_url = dashboard_url.split("/dashboard", 1)[0].rstrip("/") or "http://127.0.0.1:8001"
    return DesktopAgentConfig(
        enabled=_bool_env("DESKTOP_AGENT_ENABLED", False),
        start_backend=_bool_env("DESKTOP_AGENT_START_BACKEND", True),
        open_browser_on_wake=_bool_env("DESKTOP_AGENT_OPEN_BROWSER_ON_WAKE", True),
        dashboard_url=dashboard_url,
        backend_url=backend_url,
        backend_timeout_seconds=_int_env("DESKTOP_AGENT_BACKEND_TIMEOUT_SECONDS", 30, 3, 120),
        dashboard_timeout_seconds=_int_env("DESKTOP_AGENT_DASHBOARD_TIMEOUT_SECONDS", 10, 1, 60),
        ready_announcement=_bool_env("DESKTOP_AGENT_READY_ANNOUNCEMENT", True),
        ready_text=os.getenv("DESKTOP_AGENT_READY_TEXT", "Alle Systeme online und bereit").strip()
        or "Alle Systeme online und bereit",
        wake_engine=os.getenv("WAKE_ENGINE", "windows_speech").strip().lower() or "windows_speech",
        wake_word=os.getenv("WAKE_WORD", DEFAULT_WAKE_WORD).strip() or DEFAULT_WAKE_WORD,
        wake_confidence_threshold=_float_env("WAKE_CONFIDENCE_THRESHOLD", 0.40, 0.1, 0.99),
        wake_cooldown_ms=_int_env("WAKE_COOLDOWN_MS", 3500, 500, 60000),
        wake_listener_ready_timeout_seconds=_int_env("WAKE_LISTENER_READY_TIMEOUT_SECONDS", 15, 1, 120),
        wake_recognizer_culture=os.getenv("WAKE_RECOGNIZER_CULTURE", "auto").strip() or "auto",
        wake_accepted_transcripts=clean_accepted_transcripts(
            os.getenv("WAKE_ACCEPTED_TRANSCRIPTS", ",".join(DEFAULT_ACCEPTED_TRANSCRIPTS))
        ),
        wake_word_model_path=Path(os.getenv("WAKE_WORD_MODEL_PATH", "app/data/models/wake/jarvis.onnx")),
        command_recognition_timeout_ms=_int_env("COMMAND_RECOGNITION_TIMEOUT_MS", 9000, 1000, 30000),
        desktop_event_reconnect_delays_ms=_list_env("DESKTOP_EVENT_RECONNECT_DELAYS_MS", (1000, 2000, 5000)),
        project_root=root,
    )
