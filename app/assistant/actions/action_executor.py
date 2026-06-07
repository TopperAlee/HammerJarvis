from typing import Any

from app.agent.permissions import ActionRisk
from app.assistant.actions.action_models import is_expired
from app.assistant.actions.pending_action_store import PendingActionStore, pending_action_store
from app.assistant.tool_registry import ToolRegistry
from app.logging_utils.audit import LOG_PATH, write_audit_log


class ActionExecutor:
    """Execute pending actions only through ToolRegistry and confirmation rules."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        store: PendingActionStore | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry()
        self.store = store or pending_action_store

    def execute(self, action_id: str, confirm: bool = False) -> dict[str, Any]:
        """Execute one pending action while preserving GREEN/YELLOW/RED semantics."""
        action = self.store.get_action(action_id)
        if not action:
            return {"id": action_id, "error": True, "message": "Aktion nicht gefunden."}
        if action.get("status") != "pending":
            return {"id": action_id, "status": action.get("status"), "message": "Aktion ist nicht mehr ausstehend."}
        if is_expired(action):
            action["status"] = "expired"
            return {"id": action_id, "status": "expired", "message": "Aktion ist abgelaufen."}

        risk = ActionRisk(str(action.get("risk", ActionRisk.RED)))
        write_audit_log("assistant_action_start", {"action_id": action_id, "tool": action.get("tool_name"), "risk": risk})
        if risk == ActionRisk.RED:
            result = {"id": action_id, "status": "blocked", "risk": risk, "message": "Rote Aktionen sind blockiert."}
            self.store.mark_blocked(action_id, result)
            write_audit_log("assistant_action_end", {"action_id": action_id, "status": "blocked"})
            return result
        if risk == ActionRisk.YELLOW and not confirm:
            return {
                "id": action_id,
                "risk": risk,
                "confirmation_required": True,
                "status": "pending",
                "message": "Diese Aktion braucht eine ausdrueckliche Bestaetigung.",
            }

        # The ToolRegistry is the single execution boundary for external effects and confirmations.
        executed = self.registry.execute_tool(
            str(action.get("tool_name") or ""),
            action.get("arguments") or {},
            confirm=confirm,
        )
        if executed.get("blocked"):
            blocked = self.store.mark_blocked(action_id, executed)
            write_audit_log("assistant_action_end", {"action_id": action_id, "status": "blocked"})
            return {"status": "blocked", "action": blocked, "result": executed}
        if executed.get("confirmation_required"):
            return {"id": action_id, "status": "pending", **executed}

        updated = self.store.mark_executed(action_id, executed)
        write_audit_log("assistant_action_end", {"action_id": action_id, "status": "executed"})
        tool_result = executed.get("result", {}) if isinstance(executed, dict) else {}
        message = tool_result.get("message") if isinstance(tool_result, dict) else None
        return {
            "id": action_id,
            "status": "executed",
            "action": updated,
            "result": executed,
            "message": message or "Aktion wurde ausgeführt.",
        }
