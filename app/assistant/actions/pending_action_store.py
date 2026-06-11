import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.assistant.actions.action_models import build_pending_action, is_expired
from app.logging_utils.audit import write_audit_log


class PendingActionStore:
    """Short-lived in-memory action store for explicit user confirmation flows."""

    def __init__(self, default_ttl_minutes: int | None = None) -> None:
        self.default_ttl_minutes = default_ttl_minutes if default_ttl_minutes is not None else _expiry_minutes()
        self._actions: dict[str, dict[str, Any]] = {}
        self._last_presented_context: dict[str, Any] | None = None

    def create_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Store a pending action after normalizing risk, status and expiration."""
        created = build_pending_action(action, ttl_minutes=self.default_ttl_minutes)
        self._actions[created["id"]] = created
        write_audit_log("action_created", _audit_action(created))
        return created

    def list_pending_actions(self) -> list[dict[str, Any]]:
        """Return non-expired pending actions in creation order."""
        self.expire_old_actions()
        actions = [action for action in self._actions.values() if action.get("status") == "pending"]
        return _with_display_indices(actions)

    def present_actions(self, actions: list[dict[str, Any]], source: str = "chat") -> list[dict[str, Any]]:
        """Record the action ids for the latest numbered list shown to the user."""
        pending_ids = [
            str(action.get("id"))
            for action in actions
            if action.get("id") in self._actions and self._actions[action["id"]].get("status") == "pending"
        ]
        if not pending_ids:
            return []
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(minutes=self.default_ttl_minutes)
        self._last_presented_context = {
            "context_id": str(uuid.uuid4()),
            "presented_action_ids": pending_ids,
            "source": source,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "consumed": False,
        }
        write_audit_log(
            "action_context_created",
            {
                "context_id": self._last_presented_context["context_id"],
                "source": source,
                "action_count": len(pending_ids),
            },
        )
        for index, action_id in enumerate(pending_ids, start=1):
            action = self._actions[action_id]
            action["display_index"] = index
            write_audit_log("action_presented", {**_audit_action(action), "display_index": index})
        return _with_display_indices([self._actions[action_id] for action_id in pending_ids])

    def resolve_presented_action(self, index: int) -> dict[str, Any] | None:
        context = self.get_active_context()
        if not context:
            write_audit_log("action_confirmed_by_global_fallback_blocked", {"index": index})
            write_audit_log("action_confirmation_ambiguous", {"index": index, "reason": "missing_context"})
            return None
        ids = context.get("presented_action_ids") or []
        if index < 1 or index > len(ids):
            write_audit_log(
                "action_confirmation_failed_preserved_context",
                {"context_id": context.get("context_id"), "index": index, "reason": "index_out_of_range"},
            )
            write_audit_log("action_confirmation_ambiguous", {"index": index, "reason": "index_out_of_range"})
            return None
        action = self.get_action(str(ids[index - 1]))
        if not action or action.get("status") != "pending":
            write_audit_log(
                "action_confirmation_failed_preserved_context",
                {"context_id": context.get("context_id"), "index": index, "reason": "action_not_pending"},
            )
            write_audit_log("action_confirmation_ambiguous", {"index": index, "reason": "action_not_pending"})
            return None
        if is_expired(action):
            action["status"] = "expired"
            write_audit_log("action_expired", _audit_action(action))
            return action
        write_audit_log(
            "action_confirmed_by_context",
            {"context_id": context.get("context_id"), "index": index, **_audit_action(action)},
        )
        return action

    def resolve_single_presented_action(self) -> dict[str, Any] | None | str:
        context = self.get_active_context()
        if not context:
            write_audit_log("action_confirmation_ambiguous", {"reason": "missing_context"})
            return None
        ids = context.get("presented_action_ids") or []
        pending = [self.get_action(str(action_id)) for action_id in ids]
        pending = [action for action in pending if action and action.get("status") == "pending"]
        if len(pending) != 1:
            write_audit_log(
                "action_confirmation_failed_preserved_context",
                {"context_id": context.get("context_id"), "reason": "multiple_recent_actions", "count": len(pending)},
            )
            write_audit_log("action_confirmation_ambiguous", {"reason": "multiple_recent_actions", "count": len(pending)})
            return "ambiguous"
        write_audit_log("action_confirmed_by_context", {"context_id": context.get("context_id"), **_audit_action(pending[0])})
        return pending[0]

    def get_active_context(self) -> dict[str, Any] | None:
        context = self._last_presented_context
        if not context:
            return None
        if context.get("consumed"):
            return None
        try:
            expires_at = datetime.fromisoformat(str(context.get("expires_at")).replace("Z", "+00:00"))
        except ValueError:
            return None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            context["consumed"] = True
            write_audit_log("action_context_expired", {"context_id": context.get("context_id"), "source": context.get("source")})
            return None
        return dict(context)

    def get_active_presented_actions(self) -> list[dict[str, Any]]:
        context = self.get_active_context()
        if not context or context.get("consumed"):
            return []
        actions: list[dict[str, Any]] = []
        for action_id in context.get("presented_action_ids") or []:
            action = self.get_action(str(action_id))
            if action and action.get("status") == "pending":
                actions.append(action)
        return _with_display_indices(actions)

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        return self._actions.get(action_id)

    def reject_action(self, action_id: str) -> dict[str, Any]:
        action = self._actions.get(action_id)
        if not action:
            return {"id": action_id, "error": True, "message": "Aktion nicht gefunden."}
        action["status"] = "rejected"
        self._consume_context_for_action(action_id)
        write_audit_log("action_rejected", _audit_action(action))
        return action

    def expire_old_actions(self) -> list[dict[str, Any]]:
        expired: list[dict[str, Any]] = []
        for action in self._actions.values():
            if action.get("status") == "pending" and is_expired(action):
                action["status"] = "expired"
                write_audit_log("action_expired", _audit_action(action))
                expired.append(action)
        return expired

    def mark_executed(self, action_id: str, result: dict[str, Any]) -> dict[str, Any]:
        action = self._actions[action_id]
        action["status"] = "executed"
        action["result"] = result
        self._consume_context_for_action(action_id)
        write_audit_log("action_executed", _audit_action(action))
        return action

    def mark_blocked(self, action_id: str, result: dict[str, Any]) -> dict[str, Any]:
        action = self._actions[action_id]
        action["status"] = "blocked"
        action["result"] = result
        return action

    def clear(self) -> None:
        self._actions.clear()
        self._last_presented_context = None

    def _consume_context_for_action(self, action_id: str) -> None:
        context = self._last_presented_context
        if not context or context.get("consumed"):
            return
        if action_id not in (context.get("presented_action_ids") or []):
            return
        context["consumed"] = True
        write_audit_log("action_context_consumed", {"context_id": context.get("context_id"), "action_id": action_id})


def _with_display_indices(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, action in enumerate(actions, start=1):
        copied = dict(action)
        copied["display_index"] = index
        result.append(copied)
    return result


def _expiry_minutes() -> int:
    try:
        return int(os.getenv("ACTION_PENDING_EXPIRY_MINUTES", "10"))
    except ValueError:
        return 10


def _audit_action(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_id": action.get("id"),
        "title": action.get("title"),
        "risk": str(action.get("risk")),
        "source": action.get("source"),
        "tool_name": action.get("tool_name"),
    }


pending_action_store = PendingActionStore()
