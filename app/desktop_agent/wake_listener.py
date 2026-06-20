from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, TextIO

from app.desktop_agent.agent_status import utc_now
from app.desktop_agent.config import DesktopAgentConfig


@dataclass(frozen=True)
class WakeDecision:
    accepted: bool
    reason: str
    event: dict[str, Any] | None = None


class WakeEventProcessor:
    def __init__(self, config: DesktopAgentConfig) -> None:
        self.config = config
        self.last_accepted_ms = 0.0

    def process(
        self,
        event: dict[str, Any],
        *,
        agent_ready: bool = True,
        listener_ready: bool = True,
        listener_alive: bool = True,
        tts_active: bool = False,
        command_active: bool = False,
        processing_active: bool = False,
    ) -> WakeDecision:
        if not agent_ready or not listener_ready or not listener_alive:
            return WakeDecision(False, "not_ready")
        if tts_active:
            return WakeDecision(False, "tts_active")
        if command_active or processing_active:
            return WakeDecision(False, "busy")
        if event.get("type") != "wake_detected":
            return WakeDecision(False, "not_wake_event")
        word = str(event.get("word") or event.get("wake_word") or "").strip()
        if word.casefold() != self.config.wake_word.casefold():
            return WakeDecision(False, "wrong_wake_word")
        try:
            confidence = float(event.get("confidence") or event.get("score") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < self.config.wake_confidence_threshold:
            return WakeDecision(False, "below_threshold")
        now_ms = time.monotonic() * 1000
        if now_ms - self.last_accepted_ms < self.config.wake_cooldown_ms:
            return WakeDecision(False, "cooldown")
        self.last_accepted_ms = now_ms
        accepted = {
            "type": "wake_detected",
            "wake_word": self.config.wake_word,
            "source": "desktop_agent",
            "engine": event.get("engine", self.config.wake_engine),
            "culture": event.get("culture"),
            "recognized_as": event.get("recognized_as"),
            "confidence": round(confidence, 3),
            "timestamp": event.get("timestamp") or utc_now(),
        }
        return WakeDecision(True, "accepted", accepted)


class WindowsSpeechWakeListener:
    def __init__(self, config: DesktopAgentConfig) -> None:
        self.config = config
        self.process: subprocess.Popen[str] | None = None
        self.ready_event: dict[str, Any] | None = None
        self.last_inventory_event: dict[str, Any] | None = None
        self.last_diagnostic_summary: dict[str, Any] | None = None
        self.last_error_event: dict[str, Any] | None = None
        self.last_wake_event: dict[str, Any] | None = None
        self._stdout_events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stderr_lines: queue.Queue[str] = queue.Queue()
        self._ready_signal = threading.Event()
        self._stop_event = threading.Event()
        self._exit_queued = False
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None

    def validate(self) -> dict[str, Any]:
        if self.config.wake_engine == "openwakeword_custom":
            path = self._resolved_model_path()
            if not path.exists():
                return {
                    "ready": False,
                    "state": "DEGRADED",
                    "code": "custom_model_missing",
                    "message": "Eigenes Jarvis-Wake-Modell fehlt.",
                }
            return {
                "ready": False,
                "state": "DEGRADED",
                "code": "custom_model_not_implemented",
                "message": "openWakeWord-Custom ist vorbereitet, aber noch nicht aktiv.",
            }
        if self.config.wake_engine != "windows_speech":
            return {
                "ready": False,
                "state": "DEGRADED",
                "code": "unsupported_wake_engine",
                "message": "Wake Engine wird nicht unterstuetzt.",
            }
        script = self.config.project_root / "scripts" / "jarvis-wake-listener.ps1"
        if not script.exists():
            return {
                "ready": False,
                "state": "DEGRADED",
                "code": "listener_missing",
                "message": "Windows-Speech-Wake-Listener fehlt.",
            }
        return {"ready": True, "state": "READY", "engine": "windows_speech"}

    def start(self) -> dict[str, Any]:
        validation = self.validate()
        if not validation.get("ready"):
            return {"started": False, "code": validation.get("code"), "message": validation.get("message")}
        if self.process and self.process.poll() is None:
            return {"started": True, "pid": self.process.pid}

        self._reset_runtime_state()
        script = self.config.project_root / "scripts" / "jarvis-wake-listener.ps1"
        args = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script.resolve()),
            "-WakeWord",
            self.config.wake_word,
            "-ConfidenceThreshold",
            str(self.config.wake_confidence_threshold),
            "-RecognizerCulture",
            self.config.wake_recognizer_culture,
            "-AcceptedTranscripts",
            ",".join(self.config.wake_accepted_transcripts),
        ]
        creationflags = 0x08000000 if sys.platform.startswith("win") else 0
        self.process = subprocess.Popen(
            args,
            cwd=str(self.config.project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        self._start_reader_threads()
        return {"started": True, "pid": self.process.pid}

    def wait_for_ready(self, timeout_seconds: int | float) -> dict[str, Any]:
        if not self.process or not self.process.stdout:
            return {"ready": False, "code": "listener_stdout_unavailable", "message": "Wake Listener stdout nicht verfuegbar."}

        deadline = time.monotonic() + float(timeout_seconds)
        while time.monotonic() < deadline:
            if self._ready_signal.wait(timeout=0.05):
                return {"ready": True, "event": self.ready_event or {}, "pid": self.process.pid}
            if self.last_error_event and self.ready_event is None:
                return {
                    "ready": False,
                    "code": self.last_error_event.get("code"),
                    "message": self.last_error_event.get("message"),
                    "event": self.last_error_event,
                }
            if self.process.poll() is not None:
                return {
                    "ready": False,
                    "code": "listener_exited_before_ready",
                    "message": "Wake Listener wurde vor Ready beendet.",
                    "exit_code": self.process.returncode,
                    "stderr": self.stderr_preview(),
                }

        self.stop()
        return {"ready": False, "code": "ready_timeout", "message": "Wake Listener hat kein Ready gemeldet.", "seconds": timeout_seconds}

    def events(self) -> Iterator[dict[str, Any]]:
        while not self._stop_event.is_set() and self.process and (self.process.poll() is None or not self._stdout_events.empty()):
            try:
                event = self._stdout_events.get(timeout=0.5)
            except queue.Empty:
                continue
            yield event
        if self.process and not self._exit_queued:
            self._queue_listener_exit()
        while not self._stdout_events.empty():
            try:
                yield self._stdout_events.get_nowait()
            except queue.Empty:
                break

    def is_alive(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process else None

    def stop(self) -> None:
        self._stop_event.set()
        process = self.process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except Exception:
                pass
        for thread in (self._stdout_thread, self._stderr_thread):
            if thread and thread.is_alive():
                thread.join(timeout=2)
        self.process = None

    def stderr_preview(self, max_chars: int = 1000) -> str:
        lines: list[str] = []
        while not self._stderr_lines.empty():
            try:
                lines.append(self._stderr_lines.get_nowait())
            except queue.Empty:
                break
        return "\n".join(lines)[-max_chars:]

    def _resolved_model_path(self) -> Path:
        path = self.config.wake_word_model_path
        if not path.is_absolute():
            path = self.config.project_root / path
        return path

    def _start_reader_threads(self) -> None:
        if self.process and self.process.stdout and not (self._stdout_thread and self._stdout_thread.is_alive()):
            self._stdout_thread = threading.Thread(
                target=self._pump_stdout,
                args=(self.process.stdout,),
                name="jarvis-wake-stdout",
                daemon=True,
            )
            self._stdout_thread.start()
        if self.process and self.process.stderr and not (self._stderr_thread and self._stderr_thread.is_alive()):
            self._stderr_thread = threading.Thread(
                target=self._pump_stderr,
                args=(self.process.stderr,),
                name="jarvis-wake-stderr",
                daemon=True,
            )
            self._stderr_thread.start()

    def _pump_stdout(self, stream: TextIO) -> None:
        while not self._stop_event.is_set():
            try:
                line = stream.readline()
            except Exception:
                self._stdout_events.put({"type": "error", "code": "stdout_read_failed", "message": "Wake Listener stdout konnte nicht gelesen werden."})
                break
            if line == "":
                if self.process and self.process.poll() is not None:
                    self._queue_listener_exit()
                    break
                time.sleep(0.05)
                continue
            self._handle_listener_line(line)

    def _pump_stderr(self, stream: TextIO) -> None:
        while not self._stop_event.is_set():
            try:
                line = stream.readline()
            except Exception:
                break
            if line == "":
                if self.process and self.process.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            cleaned = " ".join(line.split())
            if cleaned:
                self._stderr_lines.put(cleaned[:500])

    def _handle_listener_line(self, line: str) -> None:
        event = parse_wake_json_line(line)
        if not event:
            return

        event_type = event.get("type")
        if event_type == "recognizer_inventory":
            self.last_inventory_event = event
            return
        if event_type == "ready":
            self.ready_event = event
            self._ready_signal.set()
            return
        if event_type == "diagnostic_summary":
            self.last_diagnostic_summary = event
            return
        if event_type == "error":
            self.last_error_event = event
            self._stdout_events.put(event)
            return
        if event_type == "wake_detected":
            normalized = self._normalize_wake_event(event)
            if normalized:
                self.last_wake_event = normalized
                self._stdout_events.put(normalized)
            return
        return

    def _normalize_wake_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        word = str(event.get("word") or event.get("wake_word") or "").strip()
        if word.casefold() != self.config.wake_word.casefold():
            return None
        try:
            confidence = float(event.get("confidence") or event.get("score") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < self.config.wake_confidence_threshold:
            return None
        return {
            "type": "wake_detected",
            "wake_word": self.config.wake_word,
            "source": "desktop_agent",
            "recognized_as": event.get("recognized_as"),
            "confidence": round(confidence, 3),
            "timestamp": event.get("timestamp") or utc_now(),
            "engine": event.get("engine", self.config.wake_engine),
            "culture": event.get("culture"),
        }

    def _queue_listener_exit(self) -> None:
        if self._exit_queued:
            return
        self._exit_queued = True
        self._ready_signal.clear()
        self._stdout_events.put({"type": "listener_exit", "exit_code": self.process.returncode if self.process else None, "stderr": self.stderr_preview()})

    def _reset_runtime_state(self) -> None:
        self.ready_event = None
        self.last_inventory_event = None
        self.last_diagnostic_summary = None
        self.last_error_event = None
        self.last_wake_event = None
        self._ready_signal.clear()
        self._stop_event.clear()
        self._exit_queued = False
        self._stdout_events = queue.Queue()
        self._stderr_lines = queue.Queue()


def parse_wake_json_line(line: str) -> dict[str, Any] | None:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
