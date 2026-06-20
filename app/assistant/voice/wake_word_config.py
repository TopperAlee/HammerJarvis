import os
from dataclasses import dataclass
from pathlib import Path


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


@dataclass(frozen=True)
class WakeWordConfig:
    enabled: bool = False
    wake_word: str = "Jarvis"
    model: str = ""
    model_path: str = ""
    threshold: float = 0.5
    cooldown_ms: int = 2500
    sample_rate: int = 16000
    frame_ms: int = 80
    command_timeout_ms: int = 8000
    max_clients: int = 1
    allowed_origins: tuple[str, ...] = ("http://127.0.0.1:8001", "http://localhost:8001")

    @property
    def expected_frame_bytes(self) -> int:
        return int(self.sample_rate * self.frame_ms / 1000) * 2

    @classmethod
    def from_env(cls) -> "WakeWordConfig":
        origins = tuple(
            item.strip().rstrip("/")
            for item in os.getenv(
                "WAKE_WORD_ALLOWED_ORIGINS",
                "http://127.0.0.1:8001;http://localhost:8001",
            ).split(";")
            if item.strip()
        )
        return cls(
            enabled=_bool_env("WAKE_WORD_ENABLED", False),
            wake_word=os.getenv("WAKE_WORD", "Jarvis").strip() or "Jarvis",
            model=os.getenv("WAKE_WORD_MODEL", "").strip(),
            model_path=os.getenv("WAKE_WORD_MODEL_PATH", "").strip(),
            threshold=_float_env("WAKE_WORD_THRESHOLD", 0.5, 0.05, 0.99),
            cooldown_ms=_int_env("WAKE_WORD_COOLDOWN_MS", 2500, 250, 30000),
            sample_rate=_int_env("WAKE_WORD_SAMPLE_RATE", 16000, 8000, 48000),
            frame_ms=_int_env("WAKE_WORD_FRAME_MS", 80, 20, 200),
            command_timeout_ms=_int_env("WAKE_WORD_COMMAND_TIMEOUT_MS", 8000, 1000, 30000),
            max_clients=_int_env("WAKE_WORD_MAX_CLIENTS", 1, 1, 4),
            allowed_origins=origins or ("http://127.0.0.1:8001", "http://localhost:8001"),
        )

    @property
    def configured_model_reference(self) -> str:
        return self.model_path or self.model

    def custom_model_missing(self) -> bool:
        if self.model_path:
            return not Path(self.model_path).exists()
        return not bool(self.model)


def get_wake_word_config() -> WakeWordConfig:
    return WakeWordConfig.from_env()
