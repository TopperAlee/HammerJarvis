from typing import Any

from app.agent.core import normalize_message
from app.agent.permissions import ActionRisk
from app.assistant.formatters.ecoflow_formatter import format_ecoflow_energy_answer
from app.assistant.formatters.mission_formatter import (
    format_daily_briefing,
    format_family_calendar_briefing,
    format_home_check,
    format_inbox_briefing,
)
from app.assistant.tool_registry import ToolRegistry
from app.logging_utils.audit import write_audit_log


MISSION_DEFINITIONS = [
    {
        "name": "daily_briefing",
        "description": "Kombiniert Gmail, TimeTree, Home Assistant und EcoFlow zu einem Tagesstatus.",
        "triggers": [
            "Tagesstatus",
            "Guten Morgen Jarvis",
            "Was ist heute wichtig?",
            "Gibt es heute etwas Wichtiges?",
            "Was muss ich heute wissen?",
        ],
    },
    {
        "name": "home_check",
        "description": "Prüft Home-Assistant-Probleme und EcoFlow-Status.",
        "triggers": ["Hauscheck", "Prüfe das Haus", "Smart Home Diagnose", "Welche Geräte sind offline?"],
    },
    {
        "name": "energy_check",
        "description": "Zeigt den aktuellen EcoFlow Energiezustand.",
        "triggers": ["Energiecheck", "Solarstatus", "Batteriestatus", "Was macht die Energie?", "EcoFlow Status"],
    },
    {
        "name": "inbox_briefing",
        "description": "Zeigt aktuelle ungelesene Gmail-Nachrichten.",
        "triggers": ["Posteingang", "Neue E-Mails", "Habe ich neue E-Mails?", "Was gibt es in Gmail?"],
    },
    {
        "name": "family_calendar_briefing",
        "description": "Zeigt heutige Termine aus TimeTree.",
        "triggers": ["TimeTree", "Familienkalender", "Was steht heute im Familienkalender?", "Welche Termine haben wir heute?"],
    },
]


class MissionController:
    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or ToolRegistry()

    def detect_mission(self, message: str) -> str | None:
        normalized = normalize_message(message)
        if _contains_any(normalized, ("tagesstatus", "guten morgen", "was ist heute wichtig", "gibt es heute etwas wichtiges", "was muss ich heute wissen")):
            return "daily_briefing"
        if _contains_any(normalized, ("hauscheck", "pruefe das haus", "prüfe das haus", "smart home diagnose", "welche geraete sind offline", "welche gerate sind offline", "welche geräte sind offline")):
            return "home_check"
        if _contains_any(normalized, ("energiecheck", "solarstatus", "batteriestatus", "was macht die energie", "ecoflow status")):
            return "energy_check"
        if _contains_any(normalized, ("posteingang", "neue e-mails", "neue emails", "neue mails", "habe ich neue e-mails", "habe ich neue emails", "was gibt es in gmail")):
            return "inbox_briefing"
        if _contains_any(normalized, ("timetree", "familienkalender", "was steht heute im familienkalender", "welche termine haben wir heute")):
            return "family_calendar_briefing"
        return None

    def run_mission(self, mission_name: str, user_message: str = "") -> dict[str, Any]:
        write_audit_log("assistant_mission_start", {"mission": mission_name})
        if mission_name == "daily_briefing":
            result = self.run_daily_briefing()
        elif mission_name == "home_check":
            result = self.run_home_check()
        elif mission_name == "energy_check":
            result = self.run_energy_check()
        elif mission_name == "inbox_briefing":
            result = self.run_inbox_briefing()
        elif mission_name == "family_calendar_briefing":
            result = self.run_family_calendar_briefing()
        else:
            raise ValueError("Unbekannte Mission.")
        write_audit_log("assistant_mission_end", {"mission": mission_name, "risk": result.get("risk")})
        return result

    def run_daily_briefing(self) -> dict[str, Any]:
        results = self._execute_tools(
            ["gmail_unread_recent", "timetree_today", "home_assistant_get_problems", "ecoflow_energy_overview"]
        )
        return self._mission_result(
            "daily_briefing",
            format_daily_briefing(results),
            results,
            ["gmail_unread_recent", "timetree_today", "home_assistant_get_problems", "ecoflow_energy_overview"],
            ["Kritische Smart-Home-Probleme prüfen.", "Wichtige ungelesene Gmail-Nachrichten lesen."],
        )

    def run_home_check(self) -> dict[str, Any]:
        results = self._execute_tools(["home_assistant_get_problems", "ecoflow_energy_overview"])
        return self._mission_result(
            "home_check",
            format_home_check(results),
            results,
            ["home_assistant_get_problems", "ecoflow_energy_overview"],
            ["Kritische Entities prüfen.", "Keine Schaltaktion wurde automatisch ausgeführt."],
        )

    def run_energy_check(self) -> dict[str, Any]:
        results = self._execute_tools(["ecoflow_energy_overview"])
        answer = format_ecoflow_energy_answer(results.get("ecoflow_energy_overview", {}))
        return self._mission_result(
            "energy_check",
            answer,
            results,
            ["ecoflow_energy_overview"],
            ["EcoFlow-Warnungen prüfen, falls vorhanden."],
        )

    def run_inbox_briefing(self) -> dict[str, Any]:
        results = self._execute_tools(["gmail_unread_recent"])
        return self._mission_result(
            "inbox_briefing",
            format_inbox_briefing(results),
            results,
            ["gmail_unread_recent"],
            ["Bei Bedarf einzelne E-Mails gezielt suchen."],
        )

    def run_family_calendar_briefing(self) -> dict[str, Any]:
        results = self._execute_tools(["timetree_today"])
        return self._mission_result(
            "family_calendar_briefing",
            format_family_calendar_briefing(results),
            results,
            ["timetree_today"],
            ["TimeTree ICS-Import prüfen, falls Termine fehlen."],
        )

    def _execute_tools(self, tool_names: list[str]) -> dict[str, Any]:
        return {tool_name: self._execute_green_tool(tool_name).get("result", {}) for tool_name in tool_names}

    def _execute_green_tool(self, tool_name: str) -> dict[str, Any]:
        tool = self.registry.get(tool_name)
        if tool.risk == ActionRisk.RED:
            return {"tool": tool_name, "risk": tool.risk, "blocked": True}
        if tool.risk == ActionRisk.YELLOW:
            return {"tool": tool_name, "risk": tool.risk, "confirmation_required": True}
        return self.registry.execute_tool(tool_name, {}, confirm=False)

    def _mission_result(
        self,
        mission: str,
        answer: str,
        tool_results: dict[str, Any],
        actions_taken: list[str],
        suggested_next_steps: list[str],
    ) -> dict[str, Any]:
        return {
            "mission": mission,
            "answer": answer,
            "tool_results": tool_results,
            "risk": "GREEN",
            "actions_taken": actions_taken,
            "suggested_next_steps": suggested_next_steps,
        }


def get_mission_definitions() -> dict[str, Any]:
    return {"missions": MISSION_DEFINITIONS}


def _contains_any(message: str, terms: tuple[str, ...]) -> bool:
    return any(term in message for term in terms)
