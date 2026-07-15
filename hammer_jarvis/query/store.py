from __future__ import annotations

from hammer_jarvis.query.models import EngineeringQueryRequest, EngineeringQueryResult


class EngineeringQueryStore:
    def __init__(self) -> None:
        self._latest: tuple[EngineeringQueryRequest, EngineeringQueryResult] | None = None

    def save(self, request: EngineeringQueryRequest, result: EngineeringQueryResult) -> None:
        self._latest = (request.model_copy(), result.model_copy(deep=True))

    def get_latest(self) -> tuple[EngineeringQueryRequest, EngineeringQueryResult] | None:
        if self._latest is None:
            return None
        request, result = self._latest
        return request.model_copy(), result.model_copy(deep=True)

    def clear(self) -> None:
        self._latest = None
