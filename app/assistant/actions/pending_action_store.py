from typing import Any

from app.assistant.actions.action_models import build_pending_action, is_expired


class PendingActionStore:
    """Short-lived in-memory action store for explicit user confirmation flows."""

    def __init__(self, default_ttl_minutes: int = 30) -> None:
        self.default_ttl_minutes = default_ttl_minutes
        self._actions: dict[str, dict[str, Any]] = {}

    def create_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Store a pending action after normalizing risk, status and expiration."""
        created = build_pending_action(action, ttl_minutes=self.default_ttl_minutes)
        self._actions[created["id"]] = created
        return created

    def list_pending_actions(self) -> list[dict[str, Any]]:
        """Return non-expired pending actions in creation order."""
        self.expire_old_actions()
        return [action for action in self._actions.values() if action.get("status") == "pending"]

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        return self._actions.get(action_id)

    def reject_action(self, action_id: str) -> dict[str, Any]:
        action = self._actions.get(action_id)
        if not action:
            return {"id": action_id, "error": True, "message": "Aktion nicht gefunden."}
        action["status"] = "rejected"
        return action

    def expire_old_actions(self) -> list[dict[str, Any]]:
        expired: list[dict[str, Any]] = []
        for action in self._actions.values():
            if action.get("status") == "pending" and is_expired(action):
                action["status"] = "expired"
                expired.append(action)
        return expired

    def mark_executed(self, action_id: str, result: dict[str, Any]) -> dict[str, Any]:
        action = self._actions[action_id]
        action["status"] = "executed"
        action["result"] = result
        return action

    def mark_blocked(self, action_id: str, result: dict[str, Any]) -> dict[str, Any]:
        action = self._actions[action_id]
        action["status"] = "blocked"
        action["result"] = result
        return action

    def clear(self) -> None:
        self._actions.clear()


pending_action_store = PendingActionStore()
