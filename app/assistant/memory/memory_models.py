from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


MEMORY_TYPES = {"fact", "preference", "correction", "project", "device", "safety_rule", "relationship", "task_context"}


def build_memory_item(data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    memory_type = str(data.get("type") or "fact")
    if memory_type not in MEMORY_TYPES:
        memory_type = "fact"
    return {
        "id": str(data.get("id") or uuid4().hex),
        "type": memory_type,
        "key": str(data.get("key") or "").strip(),
        "value": str(data.get("value") or "").strip(),
        "tags": [str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()] if isinstance(data.get("tags"), list) else [],
        "source": str(data.get("source") or "user"),
        "confidence": str(data.get("confidence") or "high"),
        "created_at": str(data.get("created_at") or now),
        "updated_at": str(data.get("updated_at") or now),
        "last_used_at": str(data.get("last_used_at") or ""),
        "protected": bool(data.get("protected", False)),
    }
