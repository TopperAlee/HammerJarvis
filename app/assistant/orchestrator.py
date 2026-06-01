import re
from typing import Any

from app.agent.core import normalize_message
from app.agent.permissions import ActionRisk
from app.assistant.llm_client import LLMClient
from app.assistant.tool_registry import ToolRegistry
from app.logging_utils.audit import write_audit_log
from app.tools.productivity.email_service import clean_email_snippet


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
            query = _build_email_search_query(message, normalized)
            result = self.registry.run("email_search_all", query=query)
            answer = (
                _gmail_error_answer()
                if _has_gmail_error(result)
                else _format_email_answer(result)
            )
            return self._tool_response("email_search_all", answer, result)

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
            return self._tool_response("calendar_today", result["message"], result)

        llm_result = self.llm_client.generate_response(message)
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
    energy_terms = ("ecoflow", "batterie", "solar", "pv", "strom", "energie")
    return any(term in message for term in energy_terms)


def _is_home_assistant_problem_intent(message: str) -> bool:
    terms = (
        "home assistant diagnose",
        "welche geraete haben probleme",
        "welche gerate haben probleme",
        "welche geräte haben probleme",
        "geraete probleme",
        "gerate probleme",
        "geräte probleme",
        "smart home status",
        "smart-home status",
        "probleme",
        "offline",
    )
    return any(term in message for term in terms)


def _is_email_search_intent(message: str) -> bool:
    terms = (
        "email",
        "mail",
        "mails",
        "e-mail",
        "e-mails",
        "posteingang",
        "nachricht",
        "nachrichten",
        "gmail",
    )
    return any(term in message for term in terms)


def _build_email_search_query(original_message: str, normalized_message: str) -> str:
    if "ungelesene" in normalized_message or "neue e-mail" in normalized_message:
        return "is:unread newer_than:30d"

    sender_match = re.search(
        r"(?:e-?mails?|mails?)\s+von\s+(.+)$",
        original_message,
        re.I,
    )
    if sender_match:
        sender = sender_match.group(1).strip(" ?!.:,;")
        if sender:
            return f"from:{sender} newer_than:90d"

    gmail_match = re.search(
        r"suche\s+gmail\s+nach\s+(.+)$",
        original_message,
        re.I,
    )
    if gmail_match:
        query = gmail_match.group(1).strip()
        if query:
            return query

    return original_message


def _has_gmail_error(result: dict[str, Any]) -> bool:
    providers = result.get("providers", [])
    return any(
        item.get("provider") == "gmail" and item.get("error") is True
        for item in providers
        if isinstance(item, dict)
    )


def _gmail_error_answer() -> str:
    return (
        "Gmail ist noch nicht korrekt verbunden. Der OAuth-Client oder das "
        "Client Secret ist ungueltig. Bitte lade die gmail_credentials.json "
        "erneut aus Google Cloud herunter. Outlook Mail ist weiterhin "
        "vorbereitet, aber noch nicht verbunden."
    )


def _format_email_answer(result: dict[str, Any]) -> str:
    lines = [str(result.get("message", "")).strip()]
    emails = _collect_emails(result)
    for index, email in enumerate(emails[:5], start=1):
        sender = str(email.get("sender") or "Unbekannter Absender").strip()
        subject = clean_email_snippet(str(email.get("subject") or "(kein Betreff)"))
        date = str(email.get("date") or "").strip()
        item = f"{index}. {sender}: {subject}"
        if date:
            item += f" ({date})"
        lines.append(item)
    return "\n".join(line for line in lines if line)


def _collect_emails(result: dict[str, Any]) -> list[dict[str, Any]]:
    emails: list[dict[str, Any]] = []
    for provider in result.get("providers", []):
        if isinstance(provider, dict) and provider.get("connected") is True:
            emails.extend(
                email
                for email in provider.get("emails", [])
                if isinstance(email, dict)
            )
    return emails


def _is_email_create_intent(message: str) -> bool:
    terms = ("schreibe", "verfasse", "erstelle", "entwurf")
    return _is_email_search_intent(message) and any(term in message for term in terms)


def _is_email_send_intent(message: str) -> bool:
    return _is_email_search_intent(message) and any(
        term in message for term in ("sende", "senden", "abschicken")
    )


def _is_calendar_today_intent(message: str) -> bool:
    calendar_terms = (
        "termin",
        "termine",
        "kalender",
        "meeting",
        "meetings",
        "heute im kalender",
        "was steht heute an",
    )
    today_terms = ("heute", "morgen", "welche", "was steht", "habe ich")
    return any(term in message for term in calendar_terms) and any(
        term in message for term in today_terms
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
