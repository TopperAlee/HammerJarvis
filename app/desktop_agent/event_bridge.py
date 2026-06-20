from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import WebSocket


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DesktopEventBridge:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.last_dashboard_heartbeat: str | None = None
        self.last_wake_event: str | None = None
        self.last_agent_heartbeat: str | None = None
        self.agent_status: dict[str, Any] = {}
        self.pending_wake_event: dict[str, Any] | None = None
        self.pending_wake_expires_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def connect_dashboard(self, websocket: WebSocket) -> None:
        pending = None
        async with self._lock:
            self.clients.add(websocket)
            self.last_dashboard_heartbeat = utc_now()
            pending = self._take_pending_wake_locked()
        if pending:
            try:
                await websocket.send_json(pending)
                self.last_wake_event = utc_now()
            except Exception:
                async with self._lock:
                    self.clients.discard(websocket)

    async def disconnect_dashboard(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.clients.discard(websocket)

    def heartbeat(self, state: str | dict[str, Any] | None = None) -> dict[str, Any]:
        self.last_agent_heartbeat = utc_now()
        if isinstance(state, dict):
            self.agent_status = dict(state)
        elif state:
            self.agent_status["agent_state"] = state
        return self.status()

    def dashboard_heartbeat(self) -> dict[str, Any]:
        self.last_dashboard_heartbeat = utc_now()
        return self.status()

    def status(self) -> dict[str, Any]:
        payload = {
            "dashboard_clients": len(self.clients),
            "last_dashboard_heartbeat": self.last_dashboard_heartbeat,
            "last_wake_event": self.last_wake_event,
            "agent_connected": self.last_agent_heartbeat is not None,
            "last_agent_heartbeat": self.last_agent_heartbeat,
            "agent_state": None,
            "backend_ready": False,
            "event_bridge_ready": False,
            "wake_listener_ready": False,
            "wake_listener_alive": False,
            "wake_listener_pid": None,
            "wake_audio_ready": False,
            "wake_audio_state": None,
            "wake_last_audio_level": None,
            "wake_last_audio_at": None,
            "wake_last_speech_detected_at": None,
            "wake_last_rejected_confidence": None,
            "wake_word": "Jarvis",
            "wake_engine": "windows_speech",
            "wake_culture": None,
            "wake_recognizer": None,
            "wake_threshold": None,
            "wake_ready_at": None,
            "last_wake_detection_at": None,
            "ready_announcement_enabled": False,
            "ready_announcement_attempted": False,
            "ready_announcement_succeeded": None,
            "ready_announcement_error": None,
            "agent_python": None,
            "backend_python": None,
            "project_root": None,
            "websocket_transport": None,
            "backend_pid": None,
            "audio_stored": False,
            "pending_wake_event": self.pending_wake_event is not None and not self._pending_expired(),
        }
        payload.update(self.agent_status)
        payload["wake_word"] = payload.get("wake_word") or "Jarvis"
        payload["wake_engine"] = payload.get("wake_engine") or "windows_speech"
        payload["audio_stored"] = False
        return payload

    async def broadcast_wake(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "type": "wake_detected",
            "wake_word": event.get("wake_word", "Jarvis"),
            "source": event.get("source", "desktop_agent"),
            "engine": event.get("engine"),
            "culture": event.get("culture"),
            "confidence": event.get("confidence"),
            "timestamp": event.get("timestamp") or self.last_wake_event,
        }
        async with self._lock:
            clients = list(self.clients)
            if not clients:
                self._store_pending_wake_locked(payload)
                return {"sent": 0, "event": payload, **self.status()}

        dead: list[WebSocket] = []
        sent = 0
        for client in clients:
            try:
                await client.send_json(payload)
                sent += 1
            except Exception:
                dead.append(client)
        async with self._lock:
            for client in dead:
                self.clients.discard(client)
            if sent > 0:
                self.last_wake_event = utc_now()
            elif len(self.clients) == 0:
                self._store_pending_wake_locked(payload)
        return {"sent": sent, "event": payload, **self.status()}

    def _store_pending_wake_locked(self, payload: dict[str, Any], ttl_seconds: int = 15) -> None:
        self.pending_wake_event = dict(payload)
        self.pending_wake_expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    def _take_pending_wake_locked(self) -> dict[str, Any] | None:
        if not self.pending_wake_event:
            return None
        if self._pending_expired():
            self.pending_wake_event = None
            self.pending_wake_expires_at = None
            return None
        pending = self.pending_wake_event
        self.pending_wake_event = None
        self.pending_wake_expires_at = None
        return pending

    def _pending_expired(self) -> bool:
        return bool(self.pending_wake_expires_at and datetime.now(timezone.utc) > self.pending_wake_expires_at)


desktop_event_bridge = DesktopEventBridge()
