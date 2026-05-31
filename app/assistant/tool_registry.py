from typing import Any

from app.agent.permissions import ActionRisk
from app.assistant.schemas import RegisteredTool
from app.tools.home_assistant import HomeAssistantTool
from app.tools.productivity.calendar_service import CalendarService
from app.tools.productivity.email_service import EmailService
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
            "general_answer",
            "Fallback fuer allgemeine Antworten.",
            ActionRisk.GREEN,
            lambda message: {"message": message},
            {"message": "string"},
            False,
        )
