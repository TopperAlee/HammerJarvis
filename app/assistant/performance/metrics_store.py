import os
import statistics
from collections import deque
from datetime import datetime, timezone
from typing import Any


class MetricsStore:
    """In-memory performance metrics store.

    Metrics intentionally contain only operation metadata and timing. They never
    store prompts, tokens, file contents, credentials, OAuth data or raw errors.
    """

    def __init__(self) -> None:
        self.max_items = _int_env("PERFORMANCE_METRICS_MAX_ITEMS", 500)
        self._items: deque[dict[str, Any]] = deque(maxlen=self.max_items)

    def add(self, item: dict[str, Any]) -> None:
        if not _enabled():
            return
        self._items.append(
            {
                "operation": str(item.get("operation") or "unknown"),
                "category": str(item.get("category") or "general"),
                "duration_ms": int(item.get("duration_ms") or 0),
                "success": bool(item.get("success", True)),
                "error_category": str(item.get("error_category") or "") if not item.get("success", True) else None,
                "timestamp": str(item.get("timestamp") or datetime.now(timezone.utc).isoformat(timespec="seconds")),
            }
        )

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._items)[-limit:]

    def slowest(self, limit: int = 10) -> list[dict[str, Any]]:
        return sorted(self._items, key=lambda item: item["duration_ms"], reverse=True)[:limit]

    def summary(self) -> dict[str, Any]:
        items = list(self._items)
        durations = [item["duration_ms"] for item in items]
        return {
            "count": len(items),
            "avg_ms": int(statistics.mean(durations)) if durations else 0,
            "p95_ms": _p95(durations),
            "errors": sum(1 for item in items if not item["success"]),
        }

    def status(self) -> dict[str, Any]:
        return {
            "enabled": _enabled(),
            "recent_operations": self.recent(25),
            "slowest_operations": self.slowest(10),
            "summary": self.summary(),
        }

def _enabled() -> bool:
    return os.getenv("PERFORMANCE_METRICS_ENABLED", "true").strip().lower() == "true"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) * 0.95) - 1))))
    return int(ordered[index])


metrics_store = MetricsStore()
