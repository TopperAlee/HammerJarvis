import asyncio

import pytest

from app.assistant.voice.wake_word_config import WakeWordConfig
from app.assistant.voice.wake_word_detector import OpenWakeWordDetector, WakeWordFrameError
from app.assistant.voice.wake_word_service import WakeWordService


class FakeWakeModel:
    def __init__(self, score: float) -> None:
        self.score = score
        self.reset_called = False

    def predict(self, audio):
        return {"jarvis_custom": self.score}

    def reset(self) -> None:
        self.reset_called = True


def test_wake_word_detector_validates_frame_size() -> None:
    config = WakeWordConfig(enabled=True, model="jarvis_custom", sample_rate=16000, frame_ms=80)
    detector = OpenWakeWordDetector(config, model=FakeWakeModel(0.9))

    with pytest.raises(WakeWordFrameError):
        detector.predict_frame(b"\x00\x00")


def test_wake_word_detector_detects_and_applies_cooldown() -> None:
    config = WakeWordConfig(
        enabled=True,
        model="jarvis_custom",
        threshold=0.5,
        cooldown_ms=30000,
        sample_rate=16000,
        frame_ms=80,
    )
    detector = OpenWakeWordDetector(config, model=FakeWakeModel(0.9))
    frame = b"\x00\x00" * int(config.sample_rate * config.frame_ms / 1000)

    first = detector.predict_frame(frame)
    second = detector.predict_frame(frame)

    assert first["detected"] is True
    assert first["score"] == 0.9
    assert second["detected"] is False


def test_wake_word_service_disabled_returns_structured_error() -> None:
    config = WakeWordConfig(enabled=False)
    service = WakeWordService(config=config, detector=OpenWakeWordDetector(config, model=FakeWakeModel(0.9)))

    result = asyncio.run(service.process_frame(b"\x00\x00" * 1280))

    assert result["type"] == "error"
    assert result["code"] == "disabled"


def test_browser_wake_word_service_is_disabled_by_default() -> None:
    config = WakeWordConfig()
    service = WakeWordService(config=config, detector=OpenWakeWordDetector(config, model=FakeWakeModel(0.9)))

    status = service.status()

    assert status["enabled"] is False
    assert status["wake_word"] == "Jarvis"


def test_hey_jarvis_is_not_active_browser_model_default() -> None:
    config = WakeWordConfig()

    assert config.model == ""
    assert config.wake_word == "Jarvis"
    assert "hey_jarvis" not in config.configured_model_reference


def test_browser_wake_event_uses_configured_wake_word() -> None:
    config = WakeWordConfig(enabled=True, wake_word="Jarvis", model="jarvis_custom", threshold=0.5)
    service = WakeWordService(config=config, detector=OpenWakeWordDetector(config, model=FakeWakeModel(0.9)))

    result = asyncio.run(service.process_frame(b"\x00\x00" * 1280))

    assert result["type"] == "wake_detected"
    assert result["wake_word"] == "Jarvis"


def test_browser_wake_missing_custom_model_reports_status(tmp_path) -> None:
    config = WakeWordConfig(enabled=True, model_path=str(tmp_path / "missing-jarvis.onnx"))
    service = WakeWordService(config=config)

    status = service.status()

    assert status["model_available"] is False
    assert status["last_error"] == "custom_model_missing"


def test_wake_word_service_origin_allowlist() -> None:
    config = WakeWordConfig(allowed_origins=("http://127.0.0.1:8001",))
    service = WakeWordService(config=config, detector=OpenWakeWordDetector(config, model=FakeWakeModel(0.1)))

    assert service.origin_allowed("http://127.0.0.1:8001") is True
    assert service.origin_allowed("http://evil.example") is False


def test_wake_word_service_rejects_extra_clients() -> None:
    config = WakeWordConfig(max_clients=1)
    service = WakeWordService(config=config, detector=OpenWakeWordDetector(config, model=FakeWakeModel(0.1)))

    async def scenario():
        first = await service.connect_client()
        second = await service.connect_client()
        await service.disconnect_client()
        return first, second

    first, second = asyncio.run(scenario())

    assert first is True
    assert second is False
