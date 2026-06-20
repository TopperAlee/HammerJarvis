from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class AgentState(str, Enum):
    STARTING = "STARTING"
    BACKEND_STARTING = "BACKEND_STARTING"
    BACKEND_READY = "BACKEND_READY"
    WAKE_ENGINE_STARTING = "WAKE_ENGINE_STARTING"
    READY = "READY"
    WAKE_DETECTED = "WAKE_DETECTED"
    DASHBOARD_STARTING = "DASHBOARD_STARTING"
    COMMAND_REQUESTED = "COMMAND_REQUESTED"
    COOLDOWN = "COOLDOWN"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"
    STOPPING = "STOPPING"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentStatus:
    state: AgentState = AgentState.STARTING
    description: str = "Desktop-Agent startet."
    updated_at: str = field(default_factory=utc_now)
    wake_engine: str = "unknown"
    wake_word: str = "Jarvis"
    backend_ready: bool = False
    event_bridge_ready: bool = False
    wake_listener_ready: bool = False
    wake_listener_alive: bool = False
    wake_listener_pid: int | None = None
    wake_audio_ready: bool = False
    wake_audio_state: str | None = None
    wake_last_audio_level: int | None = None
    wake_last_audio_at: str | None = None
    wake_last_speech_detected_at: str | None = None
    wake_last_rejected_confidence: float | None = None
    wake_culture: str | None = None
    wake_recognizer: str | None = None
    wake_threshold: float | None = None
    wake_ready_at: str | None = None
    last_wake_at: str | None = None
    last_error: str | None = None
    ready_announcement_enabled: bool = True
    ready_announcement_attempted: bool = False
    ready_announcement_succeeded: bool | None = None
    ready_announcement_error: str | None = None
    agent_python: str | None = None
    backend_python: str | None = None
    project_root: str | None = None
    websocket_transport: str | None = None
    backend_pid: int | None = None

    def transition(self, state: AgentState, description: str, *, error: str | None = None) -> None:
        self.state = state
        self.description = description
        self.updated_at = utc_now()
        if error:
            self.last_error = error

    def to_payload(self) -> dict[str, object]:
        return {
            "agent_state": self.state.value,
            "description": self.description,
            "updated_at": self.updated_at,
            "backend_ready": self.backend_ready,
            "event_bridge_ready": self.event_bridge_ready,
            "wake_listener_ready": self.wake_listener_ready,
            "wake_listener_alive": self.wake_listener_alive,
            "wake_listener_pid": self.wake_listener_pid,
            "wake_audio_ready": self.wake_audio_ready,
            "wake_audio_state": self.wake_audio_state,
            "wake_last_audio_level": self.wake_last_audio_level,
            "wake_last_audio_at": self.wake_last_audio_at,
            "wake_last_speech_detected_at": self.wake_last_speech_detected_at,
            "wake_last_rejected_confidence": self.wake_last_rejected_confidence,
            "wake_engine": self.wake_engine,
            "wake_word": self.wake_word,
            "wake_culture": self.wake_culture,
            "wake_recognizer": self.wake_recognizer,
            "wake_threshold": self.wake_threshold,
            "wake_ready_at": self.wake_ready_at,
            "last_wake_detection_at": self.last_wake_at,
            "last_error": self.last_error,
            "ready_announcement_enabled": self.ready_announcement_enabled,
            "ready_announcement_attempted": self.ready_announcement_attempted,
            "ready_announcement_succeeded": self.ready_announcement_succeeded,
            "ready_announcement_error": self.ready_announcement_error,
            "agent_python": self.agent_python,
            "backend_python": self.backend_python,
            "project_root": self.project_root,
            "websocket_transport": self.websocket_transport,
            "backend_pid": self.backend_pid,
        }
