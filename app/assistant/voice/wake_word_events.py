from datetime import datetime, timezone
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def ready_event(model: str, sample_rate: int, frame_ms: int) -> dict[str, Any]:
    return {"type": "ready", "model": model, "sample_rate": sample_rate, "frame_ms": frame_ms}


def status_event(state: str) -> dict[str, str]:
    return {"type": "status", "state": state}


def error_event(code: str, message: str) -> dict[str, str]:
    return {"type": "error", "code": code, "message": message}

