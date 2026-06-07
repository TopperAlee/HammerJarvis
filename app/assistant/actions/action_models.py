from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.agent.permissions import ActionRisk


ACTION_STATUSES = {"pending", "executed", "rejected", "blocked", "expired"}
SECRET_ARGUMENT_KEYS = {"token", "authorization", "password", "secret", "api_key"}


def build_pending_action(data: dict[str, Any], ttl_minutes: int = 30) -> dict[str, Any]:
    """Create a normalized pending action without retaining secrets or file contents."""
    now = datetime.now(timezone.utc)
    risk = _risk(data.get("risk", ActionRisk.GREEN))
    return {
        "id": str(data.get("id") or uuid4().hex),
        "title": _repair_mojibake(str(data.get("title") or "Aktion")),
        "description": _repair_mojibake(str(data.get("description") or "")),
        "tool_name": str(data.get("tool_name") or ""),
        "arguments": _sanitize_arguments(data.get("arguments") or {}),
        "risk": risk,
        "status": str(data.get("status") or "pending"),
        "created_at": str(data.get("created_at") or now.isoformat()),
        "expires_at": str(data.get("expires_at") or (now + timedelta(minutes=ttl_minutes)).isoformat()),
        "source": str(data.get("source") or "chat"),
        "requires_confirmation": bool(data.get("requires_confirmation", risk != ActionRisk.GREEN)),
    }


def is_expired(action: dict[str, Any]) -> bool:
    """Return true when an action is past its short-lived confirmation window."""
    try:
        expires_at = datetime.fromisoformat(str(action.get("expires_at")).replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def _risk(value: Any) -> ActionRisk:
    try:
        return ActionRisk(str(value))
    except ValueError:
        return ActionRisk.RED


def _sanitize_arguments(arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in arguments.items():
        lowered = str(key).lower()
        if lowered in SECRET_ARGUMENT_KEYS:
            cleaned[key] = "[REDACTED]"
        elif lowered in {"content", "file_content", "text"} and isinstance(value, str) and len(value) > 4000:
            # Keep pending actions lightweight; large document bodies must stay in tools/files, not the action store.
            cleaned[key] = value[:4000]
        else:
            cleaned[key] = value
    return cleaned


def _repair_mojibake(value: str) -> str:
    repaired = value
    for _ in range(2):
        if "Ã" not in repaired and "Â" not in repaired:
            break
        try:
            repaired = repaired.encode("latin1").decode("utf-8")
        except UnicodeError:
            break
    return repaired
