from __future__ import annotations

import signal
import sys
import time
from pathlib import Path
from typing import Any

from app.desktop_agent.agent_status import AgentState, AgentStatus
from app.desktop_agent.backend_manager import BackendManager
from app.desktop_agent.config import load_desktop_agent_config
from app.desktop_agent.dashboard_bridge import DashboardBridge
from app.desktop_agent.local_speech import LocalSpeech
from app.desktop_agent.logging_setup import configure_agent_logger
from app.desktop_agent.python_runtime import current_agent_python, preflight_python_runtime
from app.desktop_agent.single_instance import SingleInstance
from app.desktop_agent.wake_listener import WakeEventProcessor, WindowsSpeechWakeListener


class DesktopAgent:
    def __init__(
        self,
        config: Any | None = None,
        instance: Any | None = None,
        backend: Any | None = None,
        bridge: Any | None = None,
        speech: Any | None = None,
        listener: Any | None = None,
        processor: Any | None = None,
    ) -> None:
        self.config = config or load_desktop_agent_config()
        self.logger = configure_agent_logger()
        self.status = AgentStatus(
            wake_engine=self.config.wake_engine,
            wake_word=self.config.wake_word,
            wake_threshold=self.config.wake_confidence_threshold,
            ready_announcement_enabled=self.config.ready_announcement,
            project_root=str(self.config.project_root),
        )
        try:
            agent_runtime = current_agent_python(self.config.project_root)
            self.status.agent_python = str(agent_runtime.executable)
        except RuntimeError as exc:
            self.status.agent_python = ""
            self.status.last_error = str(exc)
        self.instance = instance or SingleInstance()
        self.backend = backend or BackendManager(self.config)
        self.bridge = bridge or DashboardBridge(self.config)
        self.speech = speech or LocalSpeech(self.config)
        self.listener = listener or WindowsSpeechWakeListener(self.config)
        self.processor = processor or WakeEventProcessor(self.config)
        self.running = True

    def run(self) -> int:
        if not self.instance.acquire(self.logger):
            return 0
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT, lambda *_: self.stop())
        try:
            return self._run_inner()
        finally:
            self.status.transition(AgentState.STOPPING, "Desktop-Agent beendet.")
            self.listener.stop()
            self.instance.release()

    def _run_inner(self) -> int:
        self._transition(AgentState.STARTING, "Desktop-Agent startet.")
        if not self.status.agent_python:
            self._transition(AgentState.ERROR, "Projekt-venv fehlt.", error="project_venv_missing")
            return 2
        agent_preflight = preflight_python_runtime(Path(self.status.agent_python), self.config.project_root)
        if not agent_preflight.get("ok"):
            self._transition(AgentState.ERROR, str(agent_preflight.get("message")), error=str(agent_preflight.get("code")))
            return 2
        self.status.websocket_transport = str(agent_preflight.get("websocket_transport") or "")
        self._transition(AgentState.BACKEND_STARTING, "Backend wird geprueft.")
        backend_result = self.backend.ensure_backend()
        self.logger.info("backend_result started=%s ready=%s", backend_result.get("started"), backend_result.get("ready"))
        self.status.backend_python = str(backend_result.get("backend_python") or getattr(self.backend, "backend_python", "") or "")
        self.status.backend_pid = backend_result.get("backend_pid") or getattr(self.backend, "backend_pid", None)
        self.status.websocket_transport = str(backend_result.get("websocket_transport") or self.status.websocket_transport or "")
        if not backend_result.get("ready"):
            self._transition(AgentState.ERROR, str(backend_result.get("message")), error=str(backend_result.get("code") or "backend_unavailable"))
            return 2

        self.status.backend_ready = True
        self._transition(AgentState.BACKEND_READY, "Backend ist bereit.")
        if not self.bridge.heartbeat(self.status.to_payload()):
            self._transition(AgentState.ERROR, "Desktop-Event-Bruecke ist nicht erreichbar.", error="desktop_bridge_unavailable")
            return 4
        self.status.event_bridge_ready = True

        validation = self.listener.validate()
        if not validation.get("ready"):
            self._transition(AgentState.DEGRADED, str(validation.get("message")), error=str(validation.get("code")))
            return 3

        self._transition(AgentState.WAKE_ENGINE_STARTING, "Wake Engine wird gestartet.")
        start_result = self.listener.start()
        self.status.wake_listener_pid = start_result.get("pid")
        self.logger.info("wake_listener_process started=%s pid=%s", bool(start_result.get("started")), start_result.get("pid"))
        if not start_result.get("started"):
            self._transition(AgentState.DEGRADED, str(start_result.get("message")), error=str(start_result.get("code")))
            self.bridge.heartbeat(self.status.to_payload())
            return 3

        ready_result = self.listener.wait_for_ready(self.config.wake_listener_ready_timeout_seconds)
        if not ready_result.get("ready"):
            code = str(ready_result.get("code") or "wake_listener_not_ready")
            if code == "ready_timeout":
                self.logger.error("wake_listener_timeout seconds=%s", ready_result.get("seconds"))
            if ready_result.get("exit_code") is not None:
                self.logger.error("wake_listener_exit exit_code=%s", ready_result.get("exit_code"))
            self.status.wake_listener_alive = self.listener.is_alive()
            self._transition(AgentState.DEGRADED, str(ready_result.get("message")), error=code)
            self.bridge.heartbeat(self.status.to_payload())
            return 3

        self._apply_wake_ready_event(ready_result.get("event") or {})
        self.status.wake_listener_alive = self.listener.is_alive()
        if not self.can_enter_ready_state():
            self._transition(AgentState.DEGRADED, "Wake Listener ist nicht vollstaendig bereit.", error="ready_requirements_missing")
            self.bridge.heartbeat(self.status.to_payload())
            return 3

        self._transition(AgentState.READY, "Desktop-Agent ist bereit.")
        if not self.bridge.heartbeat(self.status.to_payload()):
            self._transition(AgentState.ERROR, "Desktop-Event-Bruecke ist nicht erreichbar.", error="desktop_bridge_unavailable")
            return 4
        self._announce_ready_once()
        self.bridge.heartbeat(self.status.to_payload())

        for event in self.listener.events():
            if not self.running:
                break
            if event.get("type") == "error":
                self._transition(AgentState.DEGRADED, str(event.get("message")), error=str(event.get("code")))
                self.bridge.heartbeat(self.status.to_payload())
                continue
            if event.get("type") == "audio_status":
                self.status.wake_audio_state = event.get("audio_state")
                self.status.wake_last_audio_level = event.get("audio_level")
                self.status.wake_last_audio_at = event.get("timestamp")
                self.bridge.heartbeat(self.status.to_payload())
                continue
            if event.get("type") == "speech_detected":
                self.status.wake_last_speech_detected_at = event.get("timestamp")
                self.bridge.heartbeat(self.status.to_payload())
                continue
            if event.get("type") == "speech_rejected":
                try:
                    self.status.wake_last_rejected_confidence = float(event.get("confidence"))
                except (TypeError, ValueError):
                    self.status.wake_last_rejected_confidence = None
                self.bridge.heartbeat(self.status.to_payload())
                continue
            if event.get("type") == "listener_exit":
                exit_code = event.get("exit_code")
                self.status.wake_listener_alive = False
                self.status.wake_listener_ready = False
                self._transition(AgentState.DEGRADED, "Wake Listener wurde beendet.", error=f"wake_listener_exit_{exit_code}")
                self.logger.error("wake_listener_exit exit_code=%s", exit_code)
                self.bridge.heartbeat(self.status.to_payload())
                self._attempt_listener_restarts()
                continue

            decision = self.processor.process(
                event,
                agent_ready=self.status.state is AgentState.READY,
                listener_ready=self.status.wake_listener_ready,
                listener_alive=self.listener.is_alive(),
            )
            if not decision.accepted:
                self.logger.info("wake_ignored reason=%s", decision.reason)
                continue
            wake_event = decision.event or {}
            self.status.last_wake_at = wake_event.get("timestamp")
            self.logger.info(
                "wake_detected word=%s recognized_as=%s confidence=%s",
                wake_event.get("wake_word"),
                wake_event.get("recognized_as"),
                wake_event.get("confidence"),
            )
            self.logger.info("wake_event accepted=True")
            self._transition(AgentState.WAKE_DETECTED, "Jarvis erkannt.")
            bridge_status = self.bridge.status()
            dashboard_clients = int(bridge_status.get("dashboard_clients") or 0)
            self.logger.info("dashboard_clients=%s", dashboard_clients)
            browser_opened = self.bridge.open_dashboard_if_needed()
            self.logger.info("browser_open_requested=%s", str(browser_opened).lower())
            if dashboard_clients == 0 and browser_opened:
                self._transition(AgentState.DASHBOARD_STARTING, "Dashboard wird geoeffnet.")
                if not self.bridge.wait_for_dashboard():
                    self.logger.info("dashboard_connect_timeout=true")
                    self.logger.info("desktop_event_sent=false clients=0 reason=dashboard_connect_timeout")
                    self._transition(AgentState.COOLDOWN, "Wake-Cooldown aktiv.")
                    self._transition(AgentState.READY, "Desktop-Agent ist bereit.")
                    self.bridge.heartbeat(self.status.to_payload())
                    continue
            send_result = self.bridge.send_wake_event(wake_event)
            sent_clients = int(send_result.get("sent") or 0)
            if sent_clients <= 0:
                self.logger.info("desktop_event_sent=false clients=0 reason=no_dashboard_client")
                self._transition(AgentState.COOLDOWN, "Wake-Cooldown aktiv.")
                self._transition(AgentState.READY, "Desktop-Agent ist bereit.")
                self.bridge.heartbeat(self.status.to_payload())
                continue
            self.logger.info("desktop_event_sent=true clients=%s", sent_clients)
            self._transition(AgentState.COMMAND_REQUESTED, "Dashboard wurde zur Befehlserkennung aufgefordert.")
            self._transition(AgentState.COOLDOWN, "Wake-Cooldown aktiv.")
            self._transition(AgentState.READY, "Desktop-Agent ist bereit.")
            self.bridge.heartbeat(self.status.to_payload())
        return 0

    def stop(self) -> None:
        self.running = False
        self.listener.stop()

    def can_enter_ready_state(self) -> bool:
        return (
            self.status.backend_ready
            and self.status.event_bridge_ready
            and self.status.wake_listener_ready
            and self.status.wake_listener_alive
        )

    def _transition(self, state: AgentState, description: str, *, error: str | None = None) -> None:
        self.status.transition(state, description, error=error)
        self.logger.info("state=%s description=%s error=%s", state.value, description, error or "")

    def _apply_wake_ready_event(self, event: dict[str, Any]) -> None:
        self.status.wake_listener_ready = True
        self.status.wake_listener_pid = self.status.wake_listener_pid or getattr(self.listener, "pid", None)
        self.status.wake_audio_ready = bool(event.get("audio_ready", True))
        self.status.wake_audio_state = event.get("audio_state")
        self.status.wake_last_audio_level = event.get("audio_level")
        self.status.wake_last_audio_at = event.get("audio_at")
        self.status.wake_culture = event.get("culture")
        self.status.wake_recognizer = event.get("recognizer")
        self.status.wake_threshold = event.get("threshold", self.config.wake_confidence_threshold)
        self.status.wake_ready_at = event.get("timestamp") or self.status.updated_at
        self.logger.info(
            'wake_listener_ready engine=%s culture=%s recognizer="%s"',
            event.get("engine"),
            event.get("culture"),
            event.get("recognizer"),
        )

    def _announce_ready_once(self) -> None:
        self.logger.info("ready_announcement started=%s", bool(self.config.ready_announcement))
        result = self.speech.speak_ready_once()
        self.status.ready_announcement_attempted = bool(result.get("attempted"))
        self.status.ready_announcement_succeeded = result.get("success")
        self.status.ready_announcement_error = result.get("error")
        self.logger.info('ready_announcement success=%s error="%s"', result.get("success"), result.get("error") or "")

    def _attempt_listener_restarts(self) -> None:
        for index, delay in enumerate(self.config.wake_listener_restart_delays_seconds, start=1):
            if not self.running:
                return
            self.logger.info("wake_listener_restart attempt=%s delay_seconds=%s", index, delay)
            time.sleep(delay)
            start_result = self.listener.start()
            self.status.wake_listener_pid = start_result.get("pid")
            if not start_result.get("started"):
                continue
            ready_result = self.listener.wait_for_ready(self.config.wake_listener_ready_timeout_seconds)
            if ready_result.get("ready"):
                self._apply_wake_ready_event(ready_result.get("event") or {})
                self.status.wake_listener_alive = self.listener.is_alive()
                if self.can_enter_ready_state():
                    self._transition(AgentState.READY, "Desktop-Agent ist bereit.")
                    self.bridge.heartbeat(self.status.to_payload())
                return


def main() -> int:
    return DesktopAgent().run()


if __name__ == "__main__":
    raise SystemExit(main())
