from typing import Any

from hammer_jarvis.intent.models import ContextState


class ContextStore:
    def __init__(self) -> None:
        self._state = ContextState()

    def get(self) -> ContextState:
        return self._state.model_copy()

    def update(self, patch: dict[str, Any]) -> ContextState:
        data = self._state.model_dump()
        for key, value in patch.items():
            if key in data:
                data[key] = value
        self._state = ContextState(**data)
        return self.get()

    def reset(self) -> ContextState:
        self._state = ContextState()
        return self.get()

