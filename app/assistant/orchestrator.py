from typing import Any

from app.agent.core import normalize_message
from app.agent.permissions import ActionRisk
from app.assistant.llm_client import LLMClient
from app.assistant.tool_registry import ToolRegistry
from app.logging_utils.audit import write_audit_log


class AssistantOrchestrator:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry()
        self.llm_client = llm_client or LLMClient()

    def handle_message(self, message: str, confirm: bool = False) -> dict[str, Any]:
        normalized = normalize_message(message)

        if _is_ecoflow_intent(normalized):
            result = self.registry.run("ecoflow_energy_overview")
            answer = _format_ecoflow_answer(result)
            return self._tool_response("ecoflow_energy_overview", answer, result)

        if _is_home_assistant_problem_intent(normalized):
            result = self.registry.run("home_assistant_get_problems")
            answer = (
                "Home Assistant Diagnose: "
                f"{result.get('critical_count', 0)} kritisch, "
                f"{result.get('warning_count', 0)} Warnungen, "
                f"{result.get('informational_count', 0)} Hinweise."
            )
            return self._tool_response("home_assistant_get_problems", answer, result)

        if _is_timetree_intent(normalized):
            result = self.registry.run("timetree_status")
            return self._tool_response("timetree_status", result["message"], result)

        if _is_email_send_intent(normalized):
            result = self.registry.run("email_send_blocked")
            return {
                "mode": "rule_based",
                "tool": "email_send_blocked",
                "answer": result["message"],
                "risk": ActionRisk.RED,
                "blocked": True,
                "result": result,
            }

        if _is_email_create_intent(normalized):
            result = self.registry.run("email_create_draft")
            return {
                "mode": "rule_based",
                "tool": "email_create_draft",
                "answer": result["message"],
                "confirmation_required": True,
                "risk": ActionRisk.YELLOW,
                "proposed_action": {"tool": "email_create_draft", "message": message},
                "result": result,
            }

        if _is_email_search_intent(normalized):
            result = self.registry.run("email_search_all", query=message)
            return self._tool_response(
                "email_search_all",
                "Ich kann E-Mails grundsaetzlich verarbeiten, aber dein echtes E-Mail-Konto ist noch nicht verbunden.",
                result,
            )

        if _is_calendar_create_intent(normalized):
            result = self.registry.run("calendar_create_event")
            return {
                "mode": "rule_based",
                "tool": "calendar_create_event",
                "answer": result["message"],
                "confirmation_required": True,
                "risk": ActionRisk.YELLOW,
                "proposed_action": {"tool": "calendar_create_event", "message": message},
                "result": result,
            }

        if _is_calendar_today_intent(normalized):
            result = self.registry.run("calendar_today")
            return self._tool_response(
                "calendar_today",
                "Ich kann Kalenderfunktionen vorbereiten, aber dein echter Kalender ist noch nicht verbunden.",
                result,
            )

        llm_result = self.llm_client.answer(message)
        write_audit_log("assistant_general_answer", {"mode": llm_result["mode"]})
        return {
            "mode": llm_result["mode"],
            "tool": "general_answer",
            "answer": llm_result["answer"],
            "risk": ActionRisk.GREEN,
        }

    def _tool_response(
        self,
        tool_name: str,
        answer: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        tool = self.registry.get(tool_name)
        write_audit_log(
            "assistant_tool",
            {"tool": tool_name, "risk": tool.risk, "requires_confirmation": False},
        )
        return {
            "mode": "rule_based",
            "tool": tool_name,
            "answer": answer,
            "risk": tool.risk,
            "result": result,
        }


def _is_ecoflow_intent(message: str) -> bool:
    return any(
        term in message
        for term in (
            "ecoflow",
            "solar status",
            "energie status",
            "wie voll ist die batterie",
            "batteriestand",
        )
    )


def _is_home_assistant_problem_intent(message: str) -> bool:
    return any(
        term in message
        for term in (
            "home assistant diagnose",
            "welche geraete haben probleme",
            "welche geräte haben probleme",
            "smart home status",
            "smart-home status",
            "probleme",
        )
    )


def _is_email_search_intent(message: str) -> bool:
    return any(term in message for term in ("email", "mail", "e-mail", "posteingang", "nachricht", "e-mails"))


def _is_email_create_intent(message: str) -> bool:
    return _is_email_search_intent(message) and any(
        term in message for term in ("schreibe", "entwurf", "erstelle")
    )


def _is_email_send_intent(message: str) -> bool:
    return _is_email_search_intent(message) and any(
        term in message for term in ("sende", "senden", "abschicken")
    )


def _is_calendar_today_intent(message: str) -> bool:
    return any(term in message for term in ("termin", "kalender", "meeting")) and any(
        term in message for term in ("heute", "morgen", "welche", "was steht", "habe ich")
    )


def _is_calendar_create_intent(message: str) -> bool:
    return any(term in message for term in ("termin", "kalender", "meeting")) and any(
        term in message for term in ("erstelle", "anlegen", "eintragen", "plane")
    )


def _is_timetree_intent(message: str) -> bool:
    return "timetree" in message


def _format_ecoflow_answer(overview: dict[str, Any]) -> str:
    human_status = overview.get("human_status", {})
    headline = human_status.get("headline") or overview.get("summary")
    details = human_status.get("details", [])
    if details:
        return f"{headline}\n" + "\n".join(f"- {detail}" for detail in details)
    return str(headline or "EcoFlow Energieuebersicht ist verfuegbar.")
