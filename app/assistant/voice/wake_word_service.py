import asyncio
from typing import Any

from app.assistant.voice.wake_word_config import WakeWordConfig, get_wake_word_config
from app.assistant.voice.wake_word_detector import (
    OpenWakeWordDetector,
    WakeWordDependencyError,
    WakeWordFrameError,
)
from app.assistant.voice.wake_word_events import utc_timestamp
from app.logging_utils.audit import write_audit_log


class WakeWordService:
    def __init__(
        self,
        config: WakeWordConfig | None = None,
        detector: OpenWakeWordDetector | None = None,
    ) -> None:
        self.config = config or get_wake_word_config()
        self.detector = detector or OpenWakeWordDetector(self.config)
        self._client_count = 0
        self._listening = False
        self._lock = asyncio.Lock()
        self.last_detection_at: str | None = None
        self.last_error: str | None = None

    async def connect_client(self) -> bool:
        async with self._lock:
            if self._client_count >= self.config.max_clients:
                self.last_error = "max_clients_reached"
                return False
            self._client_count += 1
            self._listening = True
            write_audit_log("wake_word_client_connected", {"client_count": self._client_count})
            return True

    async def disconnect_client(self) -> None:
        async with self._lock:
            self._client_count = max(0, self._client_count - 1)
            self._listening = self._client_count > 0
            self.detector.reset()
            write_audit_log("wake_word_client_disconnected", {"client_count": self._client_count})

    def origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            return True
        normalized = origin.rstrip("/")
        return normalized in self.config.allowed_origins

    def status(self) -> dict[str, Any]:
        installed = self.detector.installed()
        custom_model_missing = self.config.enabled and self.config.custom_model_missing()
        return {
            "enabled": self.config.enabled,
            "installed": installed,
            "model_available": not custom_model_missing and installed and self.detector.model_available(),
            "wake_word": self.config.wake_word,
            "model": self.config.model,
            "model_path": self.config.model_path,
            "threshold": self.config.threshold,
            "cooldown_ms": self.config.cooldown_ms,
            "sample_rate": self.config.sample_rate,
            "frame_ms": self.config.frame_ms,
            "command_timeout_ms": self.config.command_timeout_ms,
            "connected": self._client_count > 0,
            "listening": self._listening,
            "client_count": self._client_count,
            "last_detection_at": self.last_detection_at,
            "last_error": self.last_error or self.detector.last_error or ("custom_model_missing" if custom_model_missing else None),
            "audio_stored": False,
        }

    async def process_frame(self, frame: bytes) -> dict[str, Any]:
        if not self.config.enabled:
            self.last_error = "disabled"
            return {"type": "error", "code": "disabled", "message": "Wake Word ist nicht aktiviert."}
        try:
            result = await asyncio.to_thread(self.detector.predict_frame, frame)
        except WakeWordFrameError as exc:
            self.last_error = str(exc)
            return {"type": "error", "code": str(exc), "message": "Ungültiger Audio-Frame."}
        except WakeWordDependencyError as exc:
            self.last_error = "model_unavailable"
            return {"type": "error", "code": "model_unavailable", "message": str(exc)}
        except Exception:
            self.last_error = "inference_error"
            return {"type": "error", "code": "inference_error", "message": "Wake-Word-Erkennung fehlgeschlagen."}
        if result.get("detected"):
            self.last_detection_at = result.get("timestamp") or utc_timestamp()
            write_audit_log(
                "wake_word_detected",
                {"model": self.config.model, "score": round(float(result.get("score") or 0), 3)},
            )
            return {
                "type": "wake_detected",
                "wake_word": self.config.wake_word,
                "score": round(float(result.get("score") or 0), 3),
                "timestamp": self.last_detection_at,
            }
        return {"type": "status", "state": "listening"}


wake_word_service = WakeWordService()
