from typing import Any
from datetime import datetime, timedelta, timezone

from hammer_jarvis.intent.models import ContextState

_last_timestamp: datetime | None = None


class ContextStore:
    def __init__(self) -> None:
        self._state = ContextState(updated_at=_now())

    def get(self) -> ContextState:
        return self._state.model_copy()

    def update(self, patch: dict[str, Any]) -> ContextState:
        data = self._state.model_dump()
        for key, value in patch.items():
            if key in data:
                data[key] = value
        data["updated_at"] = _now()
        self._state = ContextState(**data)
        return self.get()

    def reset(self) -> ContextState:
        self._state = ContextState(updated_at=_now())
        return self.get()


def _now() -> str:
    global _last_timestamp
    current = datetime.now(timezone.utc)
    if _last_timestamp is not None and current <= _last_timestamp:
        current = _last_timestamp + timedelta(microseconds=1)
    _last_timestamp = current
    return current.isoformat()
