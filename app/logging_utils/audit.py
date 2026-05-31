import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "audit.log"
SECRET_KEYS = {"token", "authorization", "password", "secret"}


def write_audit_log(action: str, detail: dict[str, Any] | None = None) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    safe_detail = _redact(detail or {})
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"{timestamp} | {action} | {json.dumps(safe_detail, sort_keys=True)}\n"
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(line)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in SECRET_KEYS:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
