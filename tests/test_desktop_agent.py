from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from types import SimpleNamespace
from pathlib import Path
from typing import Any

import pytest

from app.desktop_agent.agent_status import AgentState
from app.desktop_agent.backend_manager import BackendManager
from app.desktop_agent.config import DesktopAgentConfig, load_desktop_agent_config
from app.desktop_agent.wake_configuration import (
    build_transcript_semantics,
    clean_accepted_transcripts,
    choose_recognizer_culture,
    normalize_recognizer_inventory,
)
from app.desktop_agent.dashboard_bridge import DashboardBridge
from app.desktop_agent.local_speech import LocalSpeech
from app.desktop_agent.main import DesktopAgent
from app.desktop_agent.python_runtime import current_agent_python, preflight_python_runtime, resolve_project_python
from app.desktop_agent.single_instance import SingleInstance
from app.desktop_agent.wake_listener import (
    WakeEventProcessor,
    WindowsSpeechWakeListener,
    parse_wake_json_line,
)


class FakeInstance:
    def acquire(self, logger=None) -> bool:
        return True

    def release(self) -> None:
        pass


class FakeBackend:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready

    def ensure_backend(self) -> dict[str, Any]:
        return {"ready": self.ready, "started": False, "message": "backend"}


class FakeBridge:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready
        self.heartbeats: list[dict[str, Any]] = []
        self.sent_events: list[dict[str, Any]] = []
        self.opened = False
        self.open_count = 0
        self.wait_called = False
        self.wait_result = True
        self.dashboard_clients = 0

    def heartbeat(self, state: str | dict[str, Any] = "READY") -> bool:
        payload = state if isinstance(state, dict) else {"agent_state": state}
        self.heartbeats.append(payload)
        return self.ready

    def status(self) -> dict[str, Any]:
        return {"dashboard_clients": self.dashboard_clients}

    def open_dashboard_if_needed(self) -> bool:
        if self.dashboard_clients:
            return False
        self.opened = True
        self.open_count += 1
        return True

    def wait_for_dashboard(self) -> bool:
        self.wait_called = True
        if self.wait_result:
            self.dashboard_clients = max(self.dashboard_clients, 1)
        return self.wait_result

    def send_wake_event(self, event: dict[str, Any]) -> dict[str, Any]:
        self.sent_events.append(event)
        return {"sent": self.dashboard_clients, "event": event}


class FakeSpeech:
    def __init__(self, success: bool = True) -> None:
        self.calls = 0
        self.success = success

    def speak_ready_once(self) -> dict[str, Any]:
        self.calls += 1
        return {
            "attempted": True,
            "success": self.success,
            "error": None if self.success else "speech_failed",
        }


class FakeListener:
    def __init__(
        self,
        ready_event: dict[str, Any] | None = None,
        events: list[dict[str, Any]] | None = None,
        alive: bool = True,
        pid: int | None = 1234,
    ) -> None:
        self.ready_event = ready_event
        self._events = events or []
        self.alive = alive
        self.pid = pid
        self.started = False
        self.stopped = False

    def validate(self) -> dict[str, Any]:
        return {"ready": True, "state": "READY", "engine": "windows_speech"}

    def start(self) -> dict[str, Any]:
        self.started = True
        return {"started": True, "pid": self.pid}

    def wait_for_ready(self, timeout_seconds: int | float) -> dict[str, Any]:
        if self.ready_event is None:
            return {"ready": False, "code": "ready_timeout", "message": "timeout"}
        if self.ready_event.get("type") == "error":
            return {
                "ready": False,
                "code": self.ready_event.get("code"),
                "message": self.ready_event.get("message"),
                "event": self.ready_event,
            }
        return {"ready": True, "event": self.ready_event, "pid": self.pid}

    def events(self):
        yield from self._events

    def is_alive(self) -> bool:
        return self.alive

    def stop(self) -> None:
        self.stopped = True


class BlockingWakeStream:
    def __init__(self) -> None:
        self.lines: queue.Queue[str | None] = queue.Queue()

    def readline(self) -> str:
        line = self.lines.get(timeout=2)
        return "" if line is None else line

    def emit(self, event: dict[str, Any]) -> None:
        self.lines.put(json.dumps(event) + "\n")

    def close(self) -> None:
        self.lines.put(None)


class FakeWakeProcess:
    def __init__(self) -> None:
        self.pid = 4321
        self.returncode: int | None = None
        self.stdout = BlockingWakeStream()
        self.stderr = BlockingWakeStream()
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0
        self.stdout.close()
        self.stderr.close()

    def wait(self, timeout: int | float | None = None) -> int:
        self.returncode = 0
        return 0


def create_fake_venv(tmp_path: Path) -> tuple[Path, Path, Path]:
    scripts = tmp_path / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    pythonw = scripts / "pythonw.exe"
    python = scripts / "python.exe"
    pythonw.write_text("", encoding="utf-8")
    python.write_text("", encoding="utf-8")
    return scripts, pythonw, python


def test_desktop_agent_config_defaults(monkeypatch, tmp_path: Path) -> None:
    for name in [
        "DESKTOP_AGENT_ENABLED",
        "WAKE_ENGINE",
        "WAKE_WORD",
        "WAKE_CONFIDENCE_THRESHOLD",
        "WAKE_COOLDOWN_MS",
        "WAKE_LISTENER_READY_TIMEOUT_SECONDS",
    ]:
        monkeypatch.delenv(name, raising=False)

    config = load_desktop_agent_config(tmp_path)

    assert config.enabled is False
    assert config.wake_engine == "windows_speech"
    assert config.wake_word == "Jarvis"
    assert config.wake_confidence_threshold == 0.40
    assert config.wake_cooldown_ms == 3500
    assert config.wake_listener_ready_timeout_seconds == 15
    assert config.wake_recognizer_culture == "auto"
    assert config.wake_accepted_transcripts == ("Jarvis", "Jervis", "Dschawis")


def test_desktop_agent_config_clamps_invalid_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WAKE_CONFIDENCE_THRESHOLD", "5")
    monkeypatch.setenv("WAKE_COOLDOWN_MS", "-1")
    monkeypatch.setenv("DESKTOP_AGENT_BACKEND_TIMEOUT_SECONDS", "999")
    monkeypatch.setenv("DESKTOP_EVENT_RECONNECT_DELAYS_MS", "10,abc,999999")

    config = load_desktop_agent_config(tmp_path)

    assert config.wake_confidence_threshold == 0.99
    assert config.wake_cooldown_ms == 500
    assert config.backend_timeout_seconds == 120
    assert config.desktop_event_reconnect_delays_ms == (250, 30000)


def test_resolve_project_python_prefers_project_pythonw(tmp_path: Path) -> None:
    _, pythonw, _ = create_fake_venv(tmp_path)

    runtime = resolve_project_python(tmp_path)

    assert runtime.executable == pythonw
    assert runtime.source == "project_venv_pythonw"


def test_resolve_project_python_falls_back_to_project_python_without_global(tmp_path: Path) -> None:
    _, pythonw, python = create_fake_venv(tmp_path)
    pythonw.unlink()

    runtime = resolve_project_python(tmp_path)

    assert runtime.executable == python
    assert runtime.source == "project_venv_python"


def test_resolve_project_python_missing_venv_raises_project_venv_missing(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="project_venv_missing"):
        resolve_project_python(tmp_path)


def test_current_agent_python_rejects_global_interpreter(monkeypatch, tmp_path: Path) -> None:
    _, pythonw, _ = create_fake_venv(tmp_path)
    monkeypatch.setattr("app.desktop_agent.python_runtime.sys.executable", r"C:\Python311\pythonw.exe")

    with pytest.raises(RuntimeError, match="project_venv_mismatch"):
        current_agent_python(tmp_path)

    assert pythonw.exists()


def test_backend_manager_uses_project_venv_interpreter(monkeypatch, tmp_path: Path) -> None:
    _, pythonw, _ = create_fake_venv(tmp_path)
    manager = BackendManager(DesktopAgentConfig(project_root=tmp_path))

    assert manager._pythonw_path() == pythonw
    assert manager.backend_python == pythonw


def test_backend_manager_start_command_and_cwd(monkeypatch, tmp_path: Path) -> None:
    _, pythonw, _ = create_fake_venv(tmp_path)
    captured: dict[str, Any] = {}

    class FakePopen:
        pid = 9876

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakePopen()

    monkeypatch.setattr("app.desktop_agent.backend_manager.subprocess.Popen", fake_popen)
    manager = BackendManager(DesktopAgentConfig(project_root=tmp_path))
    manager.start_backend()

    assert captured["args"][:4] == [str(pythonw), "-m", "uvicorn", "app.main:app"]
    assert "--host" in captured["args"]
    assert "127.0.0.1" in captured["args"]
    assert "--port" in captured["args"]
    assert "8001" in captured["args"]
    assert captured["kwargs"]["cwd"] == str(tmp_path)
    assert manager.backend_pid == 9876


def _preflight_result(checks: dict[str, bool]) -> SimpleNamespace:
    payload = {"python": r"D:\Dev\projects\HammerJarvis\.venv\Scripts\pythonw.exe", "checks": checks}
    payload["websocket_transport"] = "websockets" if checks.get("websockets") else ("wsproto" if checks.get("wsproto") else "")
    return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")


def test_preflight_fails_when_fastapi_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _preflight_result({"fastapi": False, "uvicorn": True, "websockets": True, "wsproto": False}))

    result = preflight_python_runtime(tmp_path / "pythonw.exe", tmp_path)

    assert result["ok"] is False
    assert result["code"] == "fastapi_missing"


def test_preflight_fails_when_uvicorn_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _preflight_result({"fastapi": True, "uvicorn": False, "websockets": True, "wsproto": False}))

    result = preflight_python_runtime(tmp_path / "pythonw.exe", tmp_path)

    assert result["ok"] is False
    assert result["code"] == "uvicorn_missing"


def test_preflight_accepts_websockets(monkeypatch, tmp_path: Path) -> None:
    _, pythonw, python = create_fake_venv(tmp_path)
    captured: dict[str, Any] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return _preflight_result({"fastapi": True, "uvicorn": True, "websockets": True, "wsproto": False})

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = preflight_python_runtime(pythonw, tmp_path)

    assert result["ok"] is True
    assert result["websocket_transport"] == "websockets"
    assert captured["args"][0] == str(python)


def test_preflight_accepts_wsproto(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _preflight_result({"fastapi": True, "uvicorn": True, "websockets": False, "wsproto": True}))

    result = preflight_python_runtime(tmp_path / "pythonw.exe", tmp_path)

    assert result["ok"] is True
    assert result["websocket_transport"] == "wsproto"


def test_preflight_fails_when_websocket_transport_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _preflight_result({"fastapi": True, "uvicorn": True, "websockets": False, "wsproto": False}))

    result = preflight_python_runtime(tmp_path / "pythonw.exe", tmp_path)

    assert result["ok"] is False
    assert result["code"] == "websocket_transport_missing"


def test_start_desktop_agent_script_prefers_venv_and_sets_working_directory() -> None:
    content = Path("scripts/start-desktop-agent.ps1").read_text(encoding="utf-8")

    assert '(Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath' in content
    assert '".venv\\Scripts\\pythonw.exe"' in content
    assert '".venv\\Scripts\\python.exe"' in content
    assert "Start-Process -FilePath $interpreter" in content
    assert "-WorkingDirectory $projectRoot" in content
    assert "project_venv_missing" in content


def test_install_desktop_agent_uses_absolute_venv_path_and_working_directory() -> None:
    content = Path("scripts/install-desktop-agent.ps1").read_text(encoding="utf-8")

    assert '(Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath' in content
    assert '".venv\\Scripts\\pythonw.exe"' in content
    assert "New-ScheduledTaskAction" in content
    assert "-Execute $interpreter" in content
    assert '-Argument "-m app.desktop_agent.main"' in content
    assert "-WorkingDirectory $projectRoot" in content
    assert "project_venv_missing" in content


def test_single_instance_prevents_second_instance(tmp_path: Path) -> None:
    first = SingleInstance("Local\\HammerJarvisDesktopAgentTest", tmp_path / "agent.lock")
    second = SingleInstance("Local\\HammerJarvisDesktopAgentTest", tmp_path / "agent.lock")
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        first.release()
        second.release()


def test_existing_backend_is_reused(monkeypatch) -> None:
    manager = BackendManager(DesktopAgentConfig())
    started = False

    monkeypatch.setattr(manager, "is_backend_ready", lambda: True)

    def fake_start():
        nonlocal started
        started = True

    monkeypatch.setattr(manager, "start_backend", fake_start)

    result = manager.ensure_backend()

    assert result["ready"] is True
    assert result["started"] is False
    assert started is False


def test_backend_timeout_when_backend_does_not_start(monkeypatch) -> None:
    manager = BackendManager(DesktopAgentConfig(backend_timeout_seconds=3))
    calls = 0
    times = iter([0, 1, 2, 4])

    def fake_ready():
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr(manager, "is_backend_ready", fake_ready)
    monkeypatch.setattr(manager, "start_backend", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(time, "monotonic", lambda: next(times))

    result = manager.ensure_backend()

    assert result["ready"] is False
    assert result["started"] is True


def test_parse_wake_json_line() -> None:
    assert parse_wake_json_line('{"type":"ready"}') == {"type": "ready"}
    assert parse_wake_json_line("not-json") is None


def test_recognizer_inventory_is_normalized() -> None:
    inventory = normalize_recognizer_inventory(
        [
            {"Id": "de", "Name": "Deutsch", "Culture": "de-DE", "Description": "German"},
            {"id": "en", "name": "English", "culture": "en-US"},
        ]
    )

    assert inventory == [
        {"id": "de", "name": "Deutsch", "culture": "de-DE", "description": "German"},
        {"id": "en", "name": "English", "culture": "en-US", "description": ""},
    ]


def test_culture_auto_prioritizes_de_then_en() -> None:
    inventory = [{"culture": "en-US", "name": "EN"}, {"culture": "de-DE", "name": "DE"}]

    selected = choose_recognizer_culture(inventory, "auto")

    assert selected["culture"] == "de-DE"


def test_culture_auto_falls_back_to_en_us() -> None:
    inventory = [{"culture": "en-US", "name": "EN"}]

    selected = choose_recognizer_culture(inventory, "auto")

    assert selected["culture"] == "en-US"


def test_explicit_installed_culture_is_selected() -> None:
    selected = choose_recognizer_culture([{"culture": "en-US", "name": "EN"}], "en-US")

    assert selected["culture"] == "en-US"


def test_missing_explicit_culture_returns_error() -> None:
    selected = choose_recognizer_culture([{"culture": "de-DE", "name": "DE"}], "en-US")

    assert selected["error"] == "culture_not_installed"
    assert selected["installed_cultures"] == ["de-DE"]


def test_accepted_transcripts_are_cleaned_without_hey_jarvis() -> None:
    transcripts = clean_accepted_transcripts(" Jarvis, Jervis,,Jarvis, Hey Jarvis, Dschawis ")

    assert transcripts == ("Jarvis", "Jervis", "Dschawis")
    assert "Hey Jarvis" not in transcripts


def test_transcript_semantics_map_variants_to_jarvis() -> None:
    semantics = build_transcript_semantics(("Jarvis", "Jervis", "Dschawis"))

    assert semantics == {"Jarvis": "Jarvis", "Jervis": "Jarvis", "Dschawis": "Jarvis"}


def test_wake_confidence_below_threshold_is_ignored() -> None:
    processor = WakeEventProcessor(DesktopAgentConfig(wake_confidence_threshold=0.40))

    decision = processor.process({"type": "wake_detected", "word": "Jarvis", "confidence": 0.2})

    assert decision.accepted is False
    assert decision.reason == "below_threshold"


def test_wake_event_before_ready_is_ignored() -> None:
    processor = WakeEventProcessor(DesktopAgentConfig(wake_confidence_threshold=0.5))

    decision = processor.process(
        {"type": "wake_detected", "word": "Jarvis", "confidence": 0.9},
        agent_ready=False,
        listener_ready=False,
        listener_alive=False,
    )

    assert decision.accepted is False
    assert decision.reason == "not_ready"


def test_wake_confidence_above_threshold_creates_event() -> None:
    processor = WakeEventProcessor(DesktopAgentConfig(wake_confidence_threshold=0.40))

    decision = processor.process({"type": "wake_detected", "word": "Jarvis", "confidence": 0.84, "culture": "de-DE"})

    assert decision.accepted is True
    assert decision.event is not None
    assert decision.event["wake_word"] == "Jarvis"
    assert decision.event["confidence"] == 0.84
    assert decision.event["culture"] == "de-DE"


def test_wake_cooldown_prevents_duplicate_activation() -> None:
    processor = WakeEventProcessor(DesktopAgentConfig(wake_confidence_threshold=0.5, wake_cooldown_ms=3500))

    first = processor.process({"type": "wake_detected", "word": "Jarvis", "confidence": 0.9})
    second = processor.process({"type": "wake_detected", "word": "Jarvis", "confidence": 0.9})

    assert first.accepted is True
    assert second.accepted is False
    assert second.reason == "cooldown"


def test_dashboard_browser_only_opens_without_client(monkeypatch) -> None:
    bridge = DashboardBridge(DesktopAgentConfig(open_browser_on_wake=True))
    opened: list[str] = []

    monkeypatch.setattr(bridge, "status", lambda: {"dashboard_clients": 0})
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)

    assert bridge.open_dashboard_if_needed() is True
    assert opened and "source=desktop-agent" in opened[0]


def test_dashboard_browser_not_opened_when_client_exists(monkeypatch) -> None:
    bridge = DashboardBridge(DesktopAgentConfig(open_browser_on_wake=True))
    monkeypatch.setattr(bridge, "status", lambda: {"dashboard_clients": 1})
    monkeypatch.setattr("webbrowser.open", lambda url: pytest.fail("browser should not open"))

    assert bridge.open_dashboard_if_needed() is False


def test_missing_custom_wake_model_is_degraded(tmp_path: Path) -> None:
    config = DesktopAgentConfig(
        wake_engine="openwakeword_custom",
        wake_word_model_path=tmp_path / "missing.onnx",
        project_root=tmp_path,
    )

    result = WindowsSpeechWakeListener(config).validate()

    assert result["ready"] is False
    assert result["code"] == "custom_model_missing"


def _make_listener_with_fake_process(monkeypatch, tmp_path: Path) -> tuple[WindowsSpeechWakeListener, FakeWakeProcess]:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "jarvis-wake-listener.ps1").write_text("# test", encoding="utf-8")
    process = FakeWakeProcess()
    monkeypatch.setattr("app.desktop_agent.wake_listener.subprocess.Popen", lambda *args, **kwargs: process)
    listener = WindowsSpeechWakeListener(DesktopAgentConfig(project_root=tmp_path, wake_confidence_threshold=0.40))
    return listener, process


def test_listener_stdout_reader_stays_alive_after_ready_and_processes_wake(monkeypatch, tmp_path: Path) -> None:
    listener, process = _make_listener_with_fake_process(monkeypatch, tmp_path)

    assert listener.start()["started"] is True
    process.stdout.emit({"type": "ready", "engine": "windows_speech", "wake_word": "Jarvis", "culture": "de-DE", "threshold": 0.4})

    ready = listener.wait_for_ready(1)

    assert ready["ready"] is True
    assert isinstance(listener._stdout_thread, threading.Thread)
    assert listener._stdout_thread.is_alive() is True

    process.stdout.emit(
        {
            "type": "wake_detected",
            "word": "Jarvis",
            "recognized_as": "Jervis",
            "confidence": 0.514,
            "culture": "de-DE",
            "engine": "windows_speech",
        }
    )
    event = next(listener.events())

    assert event["type"] == "wake_detected"
    assert event["wake_word"] == "Jarvis"
    assert event["source"] == "desktop_agent"
    assert event["recognized_as"] == "Jervis"
    assert event["confidence"] == 0.514
    assert listener.last_wake_event == event

    listener.stop()


def test_listener_ignores_non_jarvis_words_but_accepts_jervis_and_dschawis(monkeypatch, tmp_path: Path) -> None:
    listener, process = _make_listener_with_fake_process(monkeypatch, tmp_path)
    listener.start()
    process.stdout.emit({"type": "ready", "engine": "windows_speech", "wake_word": "Jarvis"})
    assert listener.wait_for_ready(1)["ready"] is True

    process.stdout.emit({"type": "wake_detected", "word": "Computer", "recognized_as": "Computer", "confidence": 0.99})
    process.stdout.emit({"type": "wake_detected", "word": "Jarvis", "recognized_as": "Dschawis", "confidence": 0.7})

    event = next(listener.events())

    assert event["type"] == "wake_detected"
    assert event["recognized_as"] == "Dschawis"
    listener.stop()


def test_listener_malformed_inventory_unknown_and_diagnostic_events_do_not_kill_reader(monkeypatch, tmp_path: Path) -> None:
    listener, process = _make_listener_with_fake_process(monkeypatch, tmp_path)
    listener.start()
    process.stdout.lines.put("{not-json\n")
    process.stdout.emit({"type": "recognizer_inventory", "count": 1})
    process.stdout.emit({"type": "diagnostic_summary", "ready": True})
    process.stdout.emit({"type": "unknown_event"})
    process.stdout.emit({"type": "ready", "engine": "windows_speech", "wake_word": "Jarvis"})

    assert listener.wait_for_ready(1)["ready"] is True
    assert listener.last_inventory_event == {"type": "recognizer_inventory", "count": 1}
    assert listener.last_diagnostic_summary == {"type": "diagnostic_summary", "ready": True}
    assert listener._stdout_thread is not None
    assert listener._stdout_thread.is_alive() is True

    process.stdout.emit({"type": "wake_detected", "word": "Jarvis", "recognized_as": "Jervis", "confidence": 0.5})
    assert next(listener.events())["type"] == "wake_detected"
    listener.stop()


def test_listener_uses_exactly_one_stdout_reader_and_stop_joins(monkeypatch, tmp_path: Path) -> None:
    listener, process = _make_listener_with_fake_process(monkeypatch, tmp_path)

    listener.start()
    first_thread = listener._stdout_thread
    listener.start()

    assert listener._stdout_thread is first_thread
    assert isinstance(listener._stderr_thread, threading.Thread)

    listener.stop()

    assert process.terminated is True
    assert listener._stdout_thread is not None
    assert listener._stdout_thread.is_alive() is False


def test_hey_jarvis_is_not_accepted_as_jarvis() -> None:
    processor = WakeEventProcessor(DesktopAgentConfig(wake_confidence_threshold=0.5))

    decision = processor.process({"type": "wake_detected", "word": "hey jarvis", "confidence": 0.99})

    assert decision.accepted is False
    assert decision.reason == "wrong_wake_word"


def test_ready_announcement_is_spoken_once(monkeypatch) -> None:
    speech = LocalSpeech(DesktopAgentConfig(ready_text="Alle Systeme online und bereit"))
    spoken: list[str] = []

    monkeypatch.setattr(speech, "speak", lambda text: spoken.append(text) or {"attempted": True, "success": True})

    assert speech.speak_ready_once()["attempted"] is True
    assert speech.speak_ready_once()["attempted"] is False
    assert spoken == ["Alle Systeme online und bereit"]


def _agent_with(
    listener: FakeListener,
    speech: FakeSpeech | None = None,
    bridge: FakeBridge | None = None,
    config: DesktopAgentConfig | None = None,
) -> DesktopAgent:
    return DesktopAgent(
        config=config or DesktopAgentConfig(),
        instance=FakeInstance(),
        backend=FakeBackend(True),
        bridge=bridge or FakeBridge(True),
        speech=speech or FakeSpeech(True),
        listener=listener,
    )


def test_agent_does_not_enter_ready_directly_after_listener_start() -> None:
    listener = FakeListener(ready_event=None)
    speech = FakeSpeech()
    agent = _agent_with(listener, speech, config=DesktopAgentConfig(wake_listener_restart_delays_seconds=()))

    result = agent._run_inner()

    assert result == 3
    assert listener.started is True
    assert speech.calls == 0
    assert agent.status.state is AgentState.DEGRADED


def test_agent_waits_for_json_ready_before_ready_and_speech() -> None:
    listener = FakeListener(
        ready_event={
            "type": "ready",
            "engine": "windows_speech",
            "wake_word": "Jarvis",
            "culture": "de-DE",
            "recognizer": "Test Recognizer",
            "timestamp": "2026-06-20T10:00:00+00:00",
        }
    )
    speech = FakeSpeech()
    agent = _agent_with(listener, speech, config=DesktopAgentConfig(wake_listener_restart_delays_seconds=()))

    result = agent._run_inner()

    assert result == 0
    assert agent.status.state is AgentState.READY
    assert agent.status.wake_listener_ready is True
    assert agent.status.wake_listener_pid == 1234
    assert agent.status.wake_culture == "de-DE"
    assert agent.status.wake_recognizer == "Test Recognizer"
    assert speech.calls == 1


def test_ready_requires_backend_bridge_listener_and_alive_process() -> None:
    agent = _agent_with(
        FakeListener(
            ready_event={
                "type": "ready",
                "engine": "windows_speech",
                "wake_word": "Jarvis",
                "culture": "de-DE",
                "recognizer": "Test",
            },
            alive=False,
        )
    )
    agent.status.backend_ready = True
    agent.status.event_bridge_ready = True
    agent.status.wake_listener_ready = True

    assert agent.can_enter_ready_state() is False


def test_listener_error_prevents_ready() -> None:
    listener = FakeListener(ready_event={"type": "error", "code": "recognizer_unavailable", "message": "Kein Recognizer"})
    speech = FakeSpeech()
    agent = _agent_with(listener, speech)

    result = agent._run_inner()

    assert result == 3
    assert agent.status.state is AgentState.DEGRADED
    assert agent.status.last_error == "recognizer_unavailable"
    assert speech.calls == 0


def test_listener_end_after_ready_sets_degraded_and_no_second_announcement() -> None:
    listener = FakeListener(
        ready_event={"type": "ready", "engine": "windows_speech", "wake_word": "Jarvis", "culture": "de-DE", "recognizer": "Test"},
        events=[{"type": "listener_exit", "exit_code": 1}],
    )
    speech = FakeSpeech()
    agent = _agent_with(listener, speech, config=DesktopAgentConfig(wake_listener_restart_delays_seconds=()))

    result = agent._run_inner()

    assert result == 0
    assert agent.status.state is AgentState.DEGRADED
    assert agent.status.last_error == "wake_listener_exit_1"
    assert speech.calls == 1


def test_status_payload_contains_listener_and_announcement_fields() -> None:
    agent = _agent_with(
        FakeListener(ready_event={"type": "ready", "engine": "windows_speech", "wake_word": "Jarvis", "culture": "de-DE", "recognizer": "Test"})
    )
    agent.status.backend_ready = True
    agent.status.event_bridge_ready = True
    agent.status.wake_listener_ready = True
    agent.status.wake_listener_alive = True
    agent.status.wake_listener_pid = 1234
    agent.status.wake_audio_ready = True
    agent.status.wake_audio_state = "Silence"
    agent.status.wake_last_audio_level = 12
    agent.status.wake_last_speech_detected_at = "2026-06-20T10:00:00+00:00"
    agent.status.wake_last_rejected_confidence = 0.41
    agent.status.ready_announcement_attempted = True
    agent.status.ready_announcement_succeeded = True

    payload = agent.status.to_payload()

    for key in [
        "agent_state",
        "backend_ready",
        "event_bridge_ready",
        "wake_listener_ready",
        "wake_listener_alive",
        "wake_listener_pid",
        "wake_audio_ready",
        "wake_audio_state",
        "wake_last_audio_level",
        "wake_last_audio_at",
        "wake_last_speech_detected_at",
        "wake_last_rejected_confidence",
        "wake_engine",
        "wake_word",
        "wake_culture",
        "wake_recognizer",
        "wake_threshold",
        "wake_ready_at",
        "last_wake_detection_at",
        "ready_announcement_enabled",
        "ready_announcement_attempted",
        "ready_announcement_succeeded",
        "ready_announcement_error",
        "agent_python",
        "backend_python",
        "project_root",
        "websocket_transport",
        "backend_pid",
    ]:
        assert key in payload
    assert "token" not in " ".join(payload)


def test_agent_opens_browser_when_no_dashboard_client_and_forwards_wake(caplog) -> None:
    caplog.set_level("INFO")
    bridge = FakeBridge(True)
    listener = FakeListener(
        ready_event={"type": "ready", "engine": "windows_speech", "wake_word": "Jarvis", "culture": "de-DE", "recognizer": "Test"},
        events=[{"type": "wake_detected", "wake_word": "Jarvis", "recognized_as": "Jervis", "confidence": 0.514, "culture": "de-DE"}],
    )
    agent = _agent_with(listener, bridge=bridge, config=DesktopAgentConfig(wake_listener_restart_delays_seconds=()))
    agent.logger.propagate = True

    agent._run_inner()

    assert bridge.opened is True
    assert bridge.open_count == 1
    assert bridge.wait_called is True
    assert bridge.sent_events
    assert "wake_detected word=Jarvis recognized_as=Jervis confidence=0.514" in caplog.text
    assert "wake_event accepted=True" in caplog.text
    assert "dashboard_clients=0" in caplog.text
    assert "browser_open_requested=true" in caplog.text
    assert "desktop_event_sent=true clients=1" in caplog.text


def test_agent_does_not_open_browser_when_dashboard_client_connected(caplog) -> None:
    caplog.set_level("INFO")
    bridge = FakeBridge(True)
    bridge.dashboard_clients = 2
    listener = FakeListener(
        ready_event={"type": "ready", "engine": "windows_speech", "wake_word": "Jarvis", "culture": "de-DE", "recognizer": "Test"},
        events=[{"type": "wake_detected", "wake_word": "Jarvis", "recognized_as": "Dschawis", "confidence": 0.8, "culture": "de-DE"}],
    )
    agent = _agent_with(listener, bridge=bridge, config=DesktopAgentConfig(wake_listener_restart_delays_seconds=()))
    agent.logger.propagate = True

    agent._run_inner()

    assert bridge.opened is False
    assert bridge.sent_events
    assert "dashboard_clients=2" in caplog.text
    assert "browser_open_requested=false" in caplog.text
    assert "desktop_event_sent=true clients=2" in caplog.text


def test_agent_does_not_send_or_request_command_when_dashboard_connect_times_out(caplog) -> None:
    caplog.set_level("INFO")
    bridge = FakeBridge(True)
    bridge.wait_result = False
    listener = FakeListener(
        ready_event={"type": "ready", "engine": "windows_speech", "wake_word": "Jarvis", "culture": "de-DE", "recognizer": "Test"},
        events=[{"type": "wake_detected", "wake_word": "Jarvis", "recognized_as": "Jervis", "confidence": 0.514, "culture": "de-DE"}],
    )
    agent = _agent_with(listener, bridge=bridge, config=DesktopAgentConfig(wake_listener_restart_delays_seconds=()))
    agent.logger.propagate = True

    agent._run_inner()

    assert bridge.open_count == 1
    assert bridge.wait_called is True
    assert bridge.sent_events == []
    assert agent.status.state is AgentState.READY
    assert "dashboard_connect_timeout=true" in caplog.text
    assert "desktop_event_sent=false clients=0 reason=dashboard_connect_timeout" in caplog.text
    assert "desktop_event_sent=true clients=0" not in caplog.text
    assert "state=COMMAND_REQUESTED" not in caplog.text


def test_agent_sends_second_wake_after_cooldown_to_existing_client(caplog) -> None:
    caplog.set_level("INFO")
    bridge = FakeBridge(True)
    bridge.dashboard_clients = 1
    listener = FakeListener(
        ready_event={"type": "ready", "engine": "windows_speech", "wake_word": "Jarvis", "culture": "de-DE", "recognizer": "Test"},
        events=[
            {"type": "wake_detected", "wake_word": "Jarvis", "recognized_as": "Jervis", "confidence": 0.8, "culture": "de-DE"},
            {"type": "wake_detected", "wake_word": "Jarvis", "recognized_as": "Jervis", "confidence": 0.9, "culture": "de-DE"},
        ],
    )
    agent = _agent_with(
        listener,
        bridge=bridge,
        config=DesktopAgentConfig(wake_listener_restart_delays_seconds=(), wake_cooldown_ms=0),
    )
    agent.logger.propagate = True

    agent._run_inner()

    assert bridge.open_count == 0
    assert len(bridge.sent_events) == 2
    assert caplog.text.count("desktop_event_sent=true clients=1") == 2
