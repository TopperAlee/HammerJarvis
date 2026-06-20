import importlib.util
import time
from array import array
from pathlib import Path
from typing import Any

from app.assistant.voice.wake_word_config import WakeWordConfig
from app.assistant.voice.wake_word_events import utc_timestamp


class WakeWordFrameError(ValueError):
    pass


class WakeWordDependencyError(RuntimeError):
    pass


class OpenWakeWordDetector:
    """Lazy openWakeWord adapter for browser-supplied 16 kHz mono PCM frames."""

    def __init__(self, config: WakeWordConfig, model: Any | None = None) -> None:
        self.config = config
        self._model = model
        self._last_detection_ms = 0.0
        self.last_error: str | None = None

    def installed(self) -> bool:
        return importlib.util.find_spec("openwakeword") is not None

    def model_available(self) -> bool:
        if self._model is not None:
            return True
        if self.config.model_path:
            return Path(self.config.model_path).exists() and self.installed()
        return bool(self.config.model) and self.installed()

    def reset(self) -> None:
        reset = getattr(self._model, "reset", None)
        if callable(reset):
            reset()

    def predict_frame(self, frame: bytes) -> dict[str, Any]:
        self._validate_frame(frame)
        model = self._ensure_model()
        prediction = model.predict(self._pcm_to_audio_array(frame))
        score = self._extract_score(prediction)
        now_ms = time.monotonic() * 1000
        in_cooldown = now_ms - self._last_detection_ms < self.config.cooldown_ms
        detected = score >= self.config.threshold and not in_cooldown
        if detected:
            self._last_detection_ms = now_ms
        return {
            "detected": detected,
            "score": score,
            "model": self.config.configured_model_reference,
            "threshold": self.config.threshold,
            "timestamp": utc_timestamp(),
        }

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self.config.model_path:
            model_reference = Path(self.config.model_path)
            if not model_reference.exists():
                self.last_error = "custom_model_missing"
                raise WakeWordDependencyError("Custom Wake-Word-Modell fehlt.")
            wakeword_models = [str(model_reference)]
        elif self.config.model:
            wakeword_models = [self.config.model]
        else:
            self.last_error = "custom_model_missing"
            raise WakeWordDependencyError("Custom Wake-Word-Modell fehlt.")
        if not self.installed():
            self.last_error = "openwakeword_not_installed"
            raise WakeWordDependencyError("openWakeWord ist nicht installiert.")
        try:
            from openwakeword.model import Model  # type: ignore

            self._model = Model(
                wakeword_models=wakeword_models,
                inference_framework="onnx",
            )
            return self._model
        except Exception as exc:  # pragma: no cover - depends on optional package/model
            self.last_error = exc.__class__.__name__
            raise WakeWordDependencyError("Wake-Word-Modell ist nicht verfügbar.") from exc

    def _validate_frame(self, frame: bytes) -> None:
        if not isinstance(frame, (bytes, bytearray)):
            raise WakeWordFrameError("expected_binary_frame")
        if not frame:
            raise WakeWordFrameError("empty_frame")
        if len(frame) != self.config.expected_frame_bytes:
            raise WakeWordFrameError("invalid_frame_size")

    def _pcm_to_audio_array(self, frame: bytes) -> Any:
        try:
            import numpy as np  # type: ignore

            return np.frombuffer(frame, dtype="<i2")
        except Exception:
            samples = array("h")
            samples.frombytes(frame)
            return samples

    def _extract_score(self, prediction: Any) -> float:
        if isinstance(prediction, dict):
            if self.config.model and self.config.model in prediction:
                return float(prediction[self.config.model])
            normalized = self.config.model.replace("_", " ") if self.config.model else self.config.wake_word
            if normalized and normalized in prediction:
                return float(prediction[normalized])
            if self.config.wake_word in prediction:
                return float(prediction[self.config.wake_word])
            for value in prediction.values():
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        try:
            return float(prediction)
        except (TypeError, ValueError):
            return 0.0
