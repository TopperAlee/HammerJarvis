from typing import Any

from app.agent.permissions import ActionRisk
from app.assistant.schemas import RegisteredTool
from app.logging_utils.audit import write_audit_log
from app.tools.home_assistant import HomeAssistantTool
from app.tools.productivity.calendar_service import CalendarService
from app.tools.productivity.email_service import EmailService
from app.tools.productivity.providers.gmail_provider import GmailProvider
from app.tools.productivity.providers.timetree_provider import TimeTreeProvider


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._register_defaults()

    def get(self, name: str) -> RegisteredTool:
        return self._tools[name]

    def run(self, name: str, **kwargs: Any) -> dict[str, Any]:
        tool = self.get(name)
        return tool.function(**kwargs)

    def execute_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        confirm: bool = False,
    ) -> dict[str, Any]:
        tool = self.get(name)
        write_audit_log(
            "assistant_execute_tool",
            {"tool": name, "risk": tool.risk, "requires_confirmation": tool.requires_confirmation},
        )
        if tool.risk == ActionRisk.RED:
            return {"tool": name, "risk": tool.risk, "blocked": True}
        if tool.risk == ActionRisk.YELLOW and not confirm:
            return {
                "tool": name,
                "risk": tool.risk,
                "confirmation_required": True,
            }
        try:
            result = tool.function(**(arguments or {}))
        except TypeError:
            result = tool.function()
        return {
            "tool": name,
            "risk": tool.risk,
            "executed": True,
            "result": result,
        }

    def get_openai_tool_schemas(self) -> list[dict[str, Any]]:
        schemas = {
            "ecoflow_energy_overview": (
                "Reads current EcoFlow energy status from Home Assistant.",
                {},
            ),
            "home_assistant_get_problems": (
                "Gets classified Home Assistant problem entities.",
                {},
            ),
            "gmail_search": (
                "Searches Gmail read-only using a Gmail query.",
                {"query": {"type": "string"}},
            ),
            "gmail_unread_recent": (
                "Gets recent unread Gmail messages.",
                {},
            ),
            "timetree_today": (
                "Reads today's TimeTree events from local ICS import.",
                {},
            ),
            "assistant_capabilities": (
                "Returns what Hammer Jarvis can currently do.",
                {},
            ),
            "general_local_status": (
                "Returns a compact status of connected services.",
                {},
            ),
        }
        return [
            {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties.keys()),
                    "additionalProperties": False,
                },
            }
            for name, (description, properties) in schemas.items()
        ]

    def register(
        self,
        name: str,
        description: str,
        risk: ActionRisk,
        function: Any,
        parameter_schema: dict[str, Any] | None = None,
        requires_confirmation: bool = False,
    ) -> None:
        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            risk=risk,
            function=function,
            parameter_schema=parameter_schema or {},
            requires_confirmation=requires_confirmation,
        )

    def _register_defaults(self) -> None:
        ha_tool = HomeAssistantTool()
        email_service = EmailService()
        calendar_service = CalendarService()
        timetree_provider = TimeTreeProvider()
        gmail_provider = GmailProvider()

        self.register(
            "home_assistant_get_problems",
            "Listet klassifizierte Home Assistant Probleme.",
            ActionRisk.GREEN,
            ha_tool.get_problem_entities,
            {},
            False,
        )
        self.register(
            "ecoflow_energy_overview",
            "Liefert die EcoFlow Energieuebersicht.",
            ActionRisk.GREEN,
            ha_tool.get_ecoflow_energy_overview,
            {},
            False,
        )
        self.register(
            "email_search_all",
            "Sucht E-Mails ueber alle vorbereiteten Provider.",
            ActionRisk.GREEN,
            email_service.search_emails,
            {"query": "string"},
            False,
        )
        self.register(
            "gmail_search",
            "Durchsucht Gmail read-only mit einer Gmail Query.",
            ActionRisk.GREEN,
            email_service.search_emails,
            {"query": "string"},
            False,
        )
        self.register(
            "gmail_unread_recent",
            "Liest aktuelle ungelesene Gmail-Nachrichten.",
            ActionRisk.GREEN,
            lambda: email_service.search_emails("is:unread newer_than:30d"),
            {},
            False,
        )
        self.register(
            "email_create_draft",
            "Erstellt einen sicheren E-Mail-Entwurf ueber einen Provider.",
            ActionRisk.YELLOW,
            email_service.create_draft,
            {"provider": "string", "request": "EmailDraftRequest"},
            True,
        )
        self.register(
            "email_send_blocked",
            "Blockiertes Senden von E-Mails.",
            ActionRisk.RED,
            email_service.send_email,
            {},
            True,
        )
        self.register(
            "calendar_today",
            "Listet heutige Kalendertermine ueber Provider.",
            ActionRisk.GREEN,
            calendar_service.list_today_events,
            {},
            False,
        )
        self.register(
            "calendar_create_event",
            "Erstellt einen sicheren Kalenderentwurf ueber einen Provider.",
            ActionRisk.YELLOW,
            calendar_service.create_event,
            {"provider": "string", "request": "CalendarEventCreateRequest"},
            True,
        )
        self.register(
            "timetree_status",
            "Status der limitierten TimeTree-Integration.",
            ActionRisk.GREEN,
            timetree_provider.status,
            {},
            False,
        )
        self.register(
            "timetree_today",
            "Listet heutige TimeTree-Termine aus lokaler ICS-Datei.",
            ActionRisk.GREEN,
            timetree_provider.list_today_events,
            {},
            False,
        )
        self.register(
            "timetree_events",
            "Listet TimeTree-Termine aus lokaler ICS-Datei.",
            ActionRisk.GREEN,
            timetree_provider.list_events,
            {},
            False,
        )
        self.register(
            "general_answer",
            "Fallback fuer allgemeine Antworten.",
            ActionRisk.GREEN,
            lambda message: {"message": message},
            {"message": "string"},
            False,
        )
        self.register(
            "assistant_capabilities",
            "Beschreibt aktuelle Hammer Jarvis Faehigkeiten.",
            ActionRisk.GREEN,
            self._assistant_capabilities,
            {},
            False,
        )
        self.register(
            "general_local_status",
            "Kompakter lokaler Integrationsstatus.",
            ActionRisk.GREEN,
            lambda: {
                "gmail": gmail_provider.status(),
                "timetree": timetree_provider.status(),
                "outlook": "mock_disabled",
            },
            {},
            False,
        )

    def _assistant_capabilities(self) -> dict[str, Any]:
        return {
            "message": (
                "Hammer Jarvis kann EcoFlow und Home Assistant lesen, Gmail "
                "read-only durchsuchen, TimeTree per lokaler ICS-Datei lesen "
                "und vorbereitete Kalender-/E-Mail-Werkzeuge sicher verwalten. "
                "E-Mail-Senden, PLC-Schreiben und Datei-Loeschen sind blockiert."
            )
        }
