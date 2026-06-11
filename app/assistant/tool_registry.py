from typing import Any

import os
from datetime import datetime

from app.agent.permissions import ActionRisk
from app.assistant.schemas import RegisteredTool
from app.assistant.session_state import open_best_match, open_result_by_index
from app.assistant.memory.memory_store import MemoryStore
from app.logging_utils.audit import write_audit_log
from app.tools.files.content_search_tool import ContentSearchTool
from app.tools.files.file_creator import FileCreatorTool
from app.tools.files.file_inspect_tool import FileInspectTool
from app.tools.files.file_open_tool import FileOpenTool
from app.tools.files.file_search_tool import FileSearchTool
from app.tools.home_assistant import HomeAssistantTool
from app.tools.home_assistant_actions import HomeAssistantActionTool
from app.tools.home_assistant_control_broker import HomeAssistantControlBroker
from app.tools.home_assistant_entities import HomeAssistantEntityCatalog
from app.tools.productivity.calendar_service import CalendarService
from app.tools.productivity.email_service import EmailService
from app.tools.productivity.providers.gmail_provider import GmailProvider
from app.tools.productivity.providers.timetree_provider import TimeTreeProvider
from app.tools.web.web_research_tool import WebResearchTool


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
        if tool.risk in {ActionRisk.YELLOW, ActionRisk.ORANGE} and not confirm:
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
        ha_action_tool = HomeAssistantActionTool()
        ha_entity_catalog = HomeAssistantEntityCatalog()
        ha_control_broker = HomeAssistantControlBroker()
        email_service = EmailService()
        calendar_service = CalendarService()
        timetree_provider = TimeTreeProvider()
        gmail_provider = GmailProvider()
        file_creator = FileCreatorTool()
        file_search = FileSearchTool()
        content_search = ContentSearchTool()
        file_inspect = FileInspectTool()
        file_open = FileOpenTool()
        web_research = WebResearchTool()
        memory_store = MemoryStore()

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
            "home_assistant_list_allowed_actions",
            "Listet freigegebene Home-Assistant-Aktionen.",
            ActionRisk.GREEN,
            ha_action_tool.list_allowed_actions,
            {},
            False,
        )
        self.register(
            "home_assistant_discover_actionable_entities",
            "Findet sichere Home-Assistant-Kandidaten fuer die Freigabe.",
            ActionRisk.GREEN,
            ha_action_tool.discover_actionable_entities,
            {},
            False,
        )
        self.register(
            "home_assistant_prepare_action",
            "Prueft eine Home-Assistant-Aktion gegen die lokale Allowlist.",
            ActionRisk.GREEN,
            ha_action_tool.prepare_home_assistant_action,
            {"entity_name_or_id": "string", "action": "string"},
            False,
        )
        self.register(
            "home_assistant_execute_action",
            "Fuehrt eine freigegebene Home-Assistant-Aktion nach Bestaetigung aus.",
            ActionRisk.YELLOW,
            ha_action_tool.execute_home_assistant_action,
            {"entity_id": "string", "action": "string"},
            True,
        )
        self.register(
            "home_assistant_add_to_allowlist",
            "Fuegt eine sichere Entity nach Bestaetigung zur Smart-Home-Freigabe hinzu.",
            ActionRisk.YELLOW,
            ha_action_tool.add_to_allowlist,
            {"entity_id": "string", "friendly_name": "string", "domain": "string", "allowed_actions": "list"},
            True,
        )
        self.register(
            "home_assistant_remove_from_allowlist",
            "Entfernt eine Entity nach Bestaetigung aus der Smart-Home-Freigabe.",
            ActionRisk.YELLOW,
            ha_action_tool.remove_from_allowlist,
            {"entity_id": "string"},
            True,
        )
        self.register(
            "home_assistant_sync_entities",
            "Synchronisiert den lokalen Home-Assistant-Entity-Katalog read-only.",
            ActionRisk.GREEN,
            ha_entity_catalog.sync_entities,
            {"force": "boolean"},
            False,
        )
        self.register(
            "home_assistant_list_entities",
            "Listet Entities aus dem lokalen Home-Assistant-Entity-Katalog.",
            ActionRisk.GREEN,
            ha_entity_catalog.list_entities,
            {"domain": "string", "state": "string", "limit": "integer"},
            False,
        )
        self.register(
            "home_assistant_search_entities",
            "Sucht Entities im lokalen Home-Assistant-Entity-Katalog.",
            ActionRisk.GREEN,
            ha_entity_catalog.search_entities,
            {"query": "string", "domain": "string", "limit": "integer"},
            False,
        )
        self.register(
            "home_assistant_list_unavailable_entities",
            "Listet unavailable Entities aus dem lokalen Home-Assistant-Entity-Katalog.",
            ActionRisk.GREEN,
            ha_entity_catalog.list_unavailable_entities,
            {"limit": "integer"},
            False,
        )
        self.register(
            "home_assistant_list_actionable_candidates",
            "Listet potenziell freigebbare Home-Assistant-Entities ohne Rechte zu vergeben.",
            ActionRisk.GREEN,
            ha_entity_catalog.list_actionable_candidates,
            {"limit": "integer"},
            False,
        )
        self.register(
            "home_assistant_get_entity",
            "Liest Details zu einer Entity aus dem lokalen Home-Assistant-Entity-Katalog.",
            ActionRisk.GREEN,
            ha_entity_catalog.get_entity,
            {"entity_id": "string"},
            False,
        )
        self.register(
            "home_assistant_control_policy",
            "Listet die lokale Home-Assistant-Control-Policy.",
            ActionRisk.GREEN,
            ha_control_broker.list_control_policy,
            {},
            False,
        )
        self.register(
            "home_assistant_list_controllable_entities",
            "Listet nach Policy kontrollierbare Home-Assistant-Entities.",
            ActionRisk.GREEN,
            ha_control_broker.list_controllable_entities,
            {"domain": "string"},
            False,
        )
        self.register(
            "home_assistant_resolve_control_intent",
            "Loest einen Steuerbefehl in eine sichere Home-Assistant-Aktion auf.",
            ActionRisk.GREEN,
            ha_control_broker.resolve_control_intent,
            {"command": "string"},
            False,
        )
        self.register(
            "home_assistant_prepare_control_action",
            "Bereitet eine Home-Assistant-Steueraktion gemaess Control Policy vor.",
            ActionRisk.GREEN,
            ha_control_broker.prepare_control_action,
            {"entity_id": "string", "action": "string", "parameters": "dict"},
            False,
        )
        self.register(
            "home_assistant_execute_control_action",
            "Fuehrt eine vorbereitete Home-Assistant-Steueraktion nach Bestaetigung aus.",
            ActionRisk.ORANGE,
            ha_control_broker.execute_control_action,
            {"entity_id": "string", "action": "string", "parameters": "dict"},
            True,
        )
        self.register(
            "home_assistant_prepare_batch_action",
            "Bereitet eine kontrollierte Home-Assistant-Batch-Aktion vor.",
            ActionRisk.GREEN,
            ha_control_broker.prepare_batch_action,
            {"domain": "string", "action": "string"},
            False,
        )
        self.register(
            "home_assistant_execute_batch_action",
            "Fuehrt eine vorbereitete Home-Assistant-Batch-Aktion nach Bestaetigung aus.",
            ActionRisk.ORANGE,
            ha_control_broker.execute_batch_action,
            {"actions": "list"},
            True,
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
            "file_create_excel",
            "Erstellt lokale Excel-Dateien im Export-Verzeichnis.",
            ActionRisk.GREEN,
            file_creator.create_excel_file,
            {"title": "string", "sheets": "list", "filename": "string"},
            False,
        )
        self.register(
            "file_create_csv",
            "Erstellt lokale CSV-Dateien im Export-Verzeichnis.",
            ActionRisk.GREEN,
            file_creator.create_csv_file,
            {"headers": "list", "rows": "list", "filename": "string"},
            False,
        )
        self.register(
            "file_create_markdown",
            "Erstellt lokale Markdown-Dateien im Export-Verzeichnis.",
            ActionRisk.GREEN,
            file_creator.create_markdown_file,
            {"title": "string", "content": "string", "filename": "string"},
            False,
        )
        self.register(
            "file_create_json",
            "Erstellt lokale JSON-Dateien im Export-Verzeichnis.",
            ActionRisk.GREEN,
            file_creator.create_json_file,
            {"data": "dict", "filename": "string"},
            False,
        )
        self.register(
            "file_list_exports",
            "Listet lokal erzeugte Export-Dateien.",
            ActionRisk.GREEN,
            file_creator.list_exports,
            {},
            False,
        )
        self.register(
            "hauscheck_diagnostic_report",
            "Erstellt einen lokalen Diagnosebericht aus aktuellen Home-Assistant- und EcoFlow-Daten.",
            ActionRisk.GREEN,
            self._hauscheck_diagnostic_report,
            {},
            False,
        )
        self.register(
            "file_search",
            "Sucht lokale Dateien in erlaubten Verzeichnissen.",
            ActionRisk.GREEN,
            file_search.search_files,
            {"query": "string", "extensions": "list", "limit": "integer"},
            False,
        )
        self.register(
            "file_list_recent_exports",
            "Listet zuletzt erzeugte Export-Dateien.",
            ActionRisk.GREEN,
            file_search.list_recent_exports,
            {"limit": "integer"},
            False,
        )
        self.register(
            "file_open",
            "Oeffnet eine erlaubte lokale Datei mit der Windows-Standard-App.",
            ActionRisk.GREEN,
            file_open.open_file,
            {"path": "string"},
            False,
        )
        self.register(
            "file_open_latest_export",
            "Oeffnet die zuletzt erzeugte Export-Datei.",
            ActionRisk.GREEN,
            file_open.open_latest_export,
            {},
            False,
        )
        self.register(
            "file_content_search",
            "Durchsucht Inhalte lokaler Dateien in erlaubten Verzeichnissen.",
            ActionRisk.GREEN,
            content_search.search_file_contents,
            {"query": "string", "extensions": "list", "limit": "integer"},
            False,
        )
        self.register(
            "file_inspect",
            "Liest eine erlaubte lokale Datei fuer Inhaltsinspektion.",
            ActionRisk.GREEN,
            file_inspect.inspect_file,
            {"path": "string", "query": "string"},
            False,
        )
        self.register(
            "file_summarize",
            "Fasst eine erlaubte lokale Datei zusammen.",
            ActionRisk.GREEN,
            file_inspect.summarize_file,
            {"path": "string", "focus": "string"},
            False,
        )
        self.register(
            "file_extract_key_fields",
            "Extrahiert Eckdaten aus einer erlaubten lokalen Datei.",
            ActionRisk.GREEN,
            file_inspect.extract_key_fields,
            {"path": "string", "document_type": "string"},
            False,
        )
        self.register(
            "file_open_best_match",
            "Oeffnet den besten Treffer der letzten Dateisuche.",
            ActionRisk.GREEN,
            open_best_match,
            {},
            False,
        )
        self.register(
            "file_open_result_by_index",
            "Oeffnet einen Treffer der letzten Dateisuche nach Index.",
            ActionRisk.GREEN,
            open_result_by_index,
            {"index": "integer"},
            False,
        )
        self.register(
            "web_search",
            "Fuehrt eine lokale Websuche ueber SearXNG aus.",
            ActionRisk.GREEN,
            web_research.search_web,
            {"query": "string"},
            False,
        )
        self.register(
            "web_research",
            "Recherchiert online und gibt Quellen zurueck.",
            ActionRisk.GREEN,
            web_research.research,
            {"query": "string"},
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
            "energy_saving_recommendations",
            "Gibt sichere Energiesparvorschlaege aus, ohne Geraete zu schalten.",
            ActionRisk.YELLOW,
            self._energy_saving_recommendations,
            {"soc_percent": "number", "source": "string"},
            True,
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
        self.register(
            "memory_add",
            "Speichert eine explizite lokale Erinnerung.",
            ActionRisk.YELLOW,
            lambda item: memory_store.add_memory(item),
            {"item": "dict"},
            True,
        )
        self.register(
            "memory_search",
            "Sucht im lokalen Gedächtnis.",
            ActionRisk.GREEN,
            memory_store.search_memory,
            {"query": "string"},
            False,
        )

    def _assistant_capabilities(self) -> dict[str, Any]:
        return {
            "message": (
                "Hammer Jarvis kann Daily Briefing, Hauscheck, Energiecheck, "
                "Inbox Briefing und TimeTree Briefing ausfuehren. Er kann "
                "EcoFlow-Diagnosen erstellen, Home Assistant read-only lesen, "
                "Gmail read-only durchsuchen, TimeTree per lokaler ICS-Datei "
                "lesen, Sprachbefehle ueber das Dashboard verarbeiten und das "
                "lokale Ollama LLM nutzen. E-Mail-Senden, PLC-Schreiben und "
                "Datei-Loeschen sind blockiert."
            ),
            "missions": [
                "daily_briefing",
                "home_check",
                "energy_check",
                "inbox_briefing",
                "family_calendar_briefing",
            ],
            "capabilities": [
                "Voice dashboard",
                "Gmail read-only",
                "Home Assistant read-only",
                "EcoFlow diagnostics",
                "Local Ollama LLM",
            ],
        }

    def _hauscheck_diagnostic_report(self) -> dict[str, Any]:
        """GREEN/read-only report generation: only reads tools and writes a local export file."""
        ha_result = self.execute_tool("home_assistant_get_problems", {}, confirm=False).get("result", {})
        ecoflow_result = self.execute_tool("ecoflow_energy_overview", {}, confirm=False).get("result", {})
        assessment = _diagnostic_assessment(ha_result, ecoflow_result)
        content = _hauscheck_diagnostic_report_content(ha_result, ecoflow_result, assessment)
        created = self.run(
            "file_create_markdown",
            title="Hammer Jarvis Diagnosebericht",
            content=content,
            filename="hauscheck_diagnose.md",
        )
        return {
            **created,
            "message": "Diagnosebericht wurde erstellt.",
            "status": assessment["status"],
            "reason": assessment["primary_reason"],
            "next_action": assessment["next_steps"][0] if assessment["next_steps"] else "Keine direkte Aktion erforderlich.",
            "summary": _hauscheck_diagnostic_summary(ha_result, ecoflow_result, assessment),
            "home_assistant": ha_result,
            "ecoflow": ecoflow_result,
        }

    def _energy_saving_recommendations(
        self,
        soc_percent: float | int | None = None,
        source: str = "ecoflow",
    ) -> dict[str, Any]:
        """Return advisory-only energy recommendations; this tool never switches devices."""
        rounded_soc = int(round(float(soc_percent))) if soc_percent is not None else None
        return {
            "tool": "energy_saving_recommendations",
            "risk": ActionRisk.YELLOW,
            "executed": True,
            "source": source,
            "soc_percent": soc_percent,
            "no_automatic_switching": True,
            "switching_performed": False,
            "headline": (
                f"EcoFlow-Batterie kritisch niedrig: {rounded_soc} %"
                if rounded_soc is not None
                else "EcoFlow-Batterie kritisch niedrig"
            ),
            "recommendations": [
                "Starke Verbraucher vorerst vermeiden.",
                "Waschmaschine, Trockner, Heizgeräte und andere Großverbraucher nicht starten.",
                "Prüfen, ob EcoFlow aktiv geladen werden kann.",
                "PV-Erzeugung abwarten, falls tagsüber Sonne erwartet wird.",
                "EcoFlow-App oder Home Assistant prüfen, ob Entladegrenzen korrekt eingestellt sind.",
            ],
            "message": "Ich habe sichere Energiesparmaßnahmen vorgeschlagen und nichts automatisch geschaltet.",
        }


def _hauscheck_diagnostic_report_content(
    ha_result: dict[str, Any],
    ecoflow_result: dict[str, Any],
    assessment: dict[str, Any],
) -> str:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "## Metadaten",
        "- generated_by: Hammer Jarvis",
        "- report_type: hauscheck_diagnose",
        "- data_sources: Home Assistant; EcoFlow via Home Assistant",
        "- safety_mode: read-only",
        "",
        f"Erstellt am: {timestamp}",
        "",
        "## Kurzbewertung",
        f"Status: {assessment['status']}",
        "",
        "Wichtigste Punkte:",
    ]
    for finding in assessment["findings"]:
        lines.append(f"- {finding}")
    lines.extend(
        [
            "",
            "## Empfohlene nächste Schritte",
        ]
    )
    for index, step in enumerate(assessment["next_steps"], start=1):
        lines.append(f"{index}. {step}")

    lines.extend(
        [
            "",
            "## Home Assistant",
            (
                f"Home Assistant: {_count(ha_result, 'critical_count')} kritisch, "
                f"{_count(ha_result, 'warning_count')} Warnungen, "
                f"{_count(ha_result, 'informational_count')} Infos"
            ),
            "",
            "### Kritische Findings",
        ]
    )
    critical = _non_ignored_items(ha_result.get("critical") or [])
    if critical:
        for item in critical:
            lines.append(f"- {_entity_label(item)}")
    else:
        lines.append("- Keine echten kritischen Probleme.")

    lines.extend(
        [
            "",
            "### Warnungen",
        ]
    )
    warnings = list(ha_result.get("warning") or [])
    if warnings:
        for item in warnings:
            lines.append(f"- {_entity_label(item)}")
    else:
        lines.append("- Keine Warnungen gemeldet.")

    lines.extend(
        [
            "",
            "### Informational",
        ]
    )
    informational = [item for item in list(ha_result.get("informational") or []) if not _is_ignored_item(item)]
    if informational:
        for item in informational:
            lines.append(f"- {_entity_label(item)}")
    else:
        lines.append("- Keine relevanten Infos.")

    lines.extend(
        [
            "",
            "## EcoFlow",
            f"Batterie: {_format_number(ecoflow_result.get('soc_percent'))} %",
            f"PV-Leistung: {_format_number(ecoflow_result.get('pv_power_w'))} W",
            f"LAN Smart Meter: {_format_number(ecoflow_result.get('smart_meter_w'))} W",
            f"Netzleistung System: {_format_number(ecoflow_result.get('grid_power_w'))} W",
            f"Batterieleistung roh: {_format_number(ecoflow_result.get('battery_power_w'))} W",
            "Die Richtung wird nicht interpretiert.",
            "",
            "### EcoFlow-Hinweise",
        ]
    )
    eco_warnings = _non_ignored_warnings(ecoflow_result.get("warnings") or [])
    if eco_warnings:
        for warning in eco_warnings:
            lines.append(f"- {_warning_message(warning)}")
    else:
        lines.append("- Keine Hinweise gemeldet.")

    ignored = _ignored_entities(ha_result, ecoflow_result)
    lines.extend(["", "## Ignorierte bekannte Entities"])
    if ignored:
        for item in ignored:
            lines.append(f"- {item}")
    else:
        lines.append("- Keine.")

    lines.extend(
        [
            "",
            "## Sicherheitshinweis",
            "Jarvis hat nichts automatisch geschaltet oder verändert.",
        ]
    )
    return "\n".join(lines)


def _legacy_hauscheck_diagnostic_report_content(ha_result: dict[str, Any], ecoflow_result: dict[str, Any]) -> str:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        f"Erstellt am: {timestamp}",
        "",
        "## Home Assistant",
        (
            f"Home Assistant: {_count(ha_result, 'critical_count')} kritisch, "
            f"{_count(ha_result, 'warning_count')} Warnungen, "
            f"{_count(ha_result, 'informational_count')} Infos"
        ),
        "",
        "### Warnungen",
    ]
    warnings = list(ha_result.get("warning") or [])
    if warnings:
        for item in warnings:
            lines.append(f"- {_entity_label(item)}")
    else:
        lines.append("- Keine Warnungen gemeldet.")

    critical = list(ha_result.get("critical") or [])
    if critical:
        lines.extend(["", "### Kritisch"])
        for item in critical:
            lines.append(f"- {_entity_label(item)}")

    lines.extend(
        [
            "",
            "## EcoFlow",
            f"Batterie: {_format_number(ecoflow_result.get('soc_percent'))} %",
            f"PV-Leistung: {_format_number(ecoflow_result.get('pv_power_w'))} W",
            f"LAN Smart Meter: {_format_number(ecoflow_result.get('smart_meter_w'))} W",
            f"Netzleistung System: {_format_number(ecoflow_result.get('grid_power_w'))} W",
            f"Batterieleistung roh: {_format_number(ecoflow_result.get('battery_power_w'))} W",
            "",
            "### EcoFlow-Hinweise",
        ]
    )
    eco_warnings = list(ecoflow_result.get("warnings") or [])
    if eco_warnings:
        for warning in eco_warnings:
            if isinstance(warning, dict):
                lines.append(f"- {warning.get('message') or warning.get('code') or warning}")
            else:
                lines.append(f"- {warning}")
    else:
        lines.append("- Keine Hinweise gemeldet.")
    return "\n".join(lines)


def _hauscheck_diagnostic_summary(
    ha_result: dict[str, Any],
    ecoflow_result: dict[str, Any],
    assessment: dict[str, Any],
) -> str:
    critical = _count(ha_result, "critical_count")
    warnings = _count(ha_result, "warning_count")
    info = _count(ha_result, "informational_count")
    soc = _format_number(ecoflow_result.get("soc_percent"))
    pv = _format_number(ecoflow_result.get("pv_power_w"))
    hints = "Hinweise vorhanden" if ecoflow_result.get("warnings") else "keine Hinweise"
    critical_text = "keine echten kritischen Probleme" if critical == 0 else f"{critical} kritische Probleme"
    return (
        f"Status: {assessment['status']}. Grund: {assessment['primary_reason']}. "
        f"Home Assistant: {critical_text}, {warnings} Warnungen, {info} Infos. "
        f"EcoFlow: Batterie {soc} %, PV {pv} W, {hints}."
    )


def _diagnostic_assessment(ha_result: dict[str, Any], ecoflow_result: dict[str, Any]) -> dict[str, Any]:
    """Calculate report severity from actionable facts, excluding known optional ignored entities."""
    soc = _float_or_none(ecoflow_result.get("soc_percent"))
    threshold = _low_battery_threshold()
    ha_critical = _non_ignored_items(ha_result.get("critical") or [])
    ha_warnings = list(ha_result.get("warning") or [])
    eco_warnings = _non_ignored_warnings(ecoflow_result.get("warnings") or [])
    stale_count = sum(1 for warning in eco_warnings if _is_stale_warning(warning))

    findings: list[str] = []
    next_steps: list[str] = []

    if soc is not None and soc <= 10:
        findings.append(f"EcoFlow-Batterie kritisch niedrig: {_format_number(soc)} %")
        next_steps.extend(["EcoFlow-Batterie prüfen.", "Starke Verbraucher vermeiden, solange die Batterie niedrig ist."])
    elif soc is not None and soc <= threshold:
        findings.append(f"EcoFlow-Batterie niedrig: {_format_number(soc)} %")
        next_steps.extend(["EcoFlow-Batterie prüfen.", "Starke Verbraucher vermeiden, solange die Batterie niedrig ist."])

    if ha_critical:
        findings.append(f"Home Assistant: {len(ha_critical)} echte kritische Probleme")
        next_steps.append("Kritische Home-Assistant-Entities prüfen.")
    else:
        findings.append("Home Assistant: keine echten kritischen Probleme")

    if ha_warnings:
        backup_count = sum(1 for item in ha_warnings if "backup" in str(item).lower())
        if backup_count:
            findings.append(f"{len(ha_warnings)} Home-Assistant-Warnungen zu Backup-Sensoren")
            next_steps.append("Home-Assistant-Backup-Konfiguration prüfen.")
        else:
            findings.append(f"{len(ha_warnings)} Home-Assistant-Warnungen")
            next_steps.append("Home-Assistant-Warnungen prüfen.")

    if stale_count >= 2:
        findings.append("Einige EcoFlow-Tageswerte sind veraltet")
        next_steps.append("EcoFlow-Tageswerte später erneut prüfen.")
    elif eco_warnings:
        findings.append("EcoFlow-Hinweise vorhanden")
        next_steps.append("EcoFlow-Hinweise prüfen.")

    # Ignored optional entities are documented separately; they must not promote severity to critical.
    if ha_critical or (soc is not None and soc <= 10):
        status = "KRITISCH"
    elif (soc is not None and soc <= threshold) or ha_warnings or stale_count >= 2 or eco_warnings:
        status = "WARNUNG"
    else:
        status = "OK"

    if not next_steps:
        next_steps.append("Keine direkte Aktion erforderlich.")
    return {
        "status": status,
        "findings": findings,
        "next_steps": _dedupe(next_steps),
        "primary_reason": findings[0] if findings else "Keine relevanten Probleme erkannt",
    }


def _non_ignored_items(items: list[Any]) -> list[Any]:
    return [item for item in items if not _is_ignored_item(item)]


def _non_ignored_warnings(warnings: list[Any]) -> list[Any]:
    return [warning for warning in warnings if not _is_ignored_warning(warning)]


def _ignored_entities(ha_result: dict[str, Any], ecoflow_result: dict[str, Any]) -> list[str]:
    ignored: list[str] = []
    for item in [*(ha_result.get("critical") or []), *(ha_result.get("warning") or []), *(ha_result.get("informational") or [])]:
        if _is_ignored_item(item):
            ignored.append(_entity_label(item))
    for warning in ecoflow_result.get("warnings") or []:
        if _is_ignored_warning(warning):
            if isinstance(warning, dict):
                ignored.append(str(warning.get("source_entity_id") or warning.get("message") or warning))
            else:
                ignored.append(str(warning))
    return _dedupe(ignored)


def _is_ignored_item(item: Any) -> bool:
    return isinstance(item, dict) and bool(item.get("ignored"))


def _is_ignored_warning(warning: Any) -> bool:
    return isinstance(warning, dict) and (warning.get("code") == "entity_ignored" or warning.get("severity") == "info")


def _is_stale_warning(warning: Any) -> bool:
    text = str(warning.get("code") if isinstance(warning, dict) else warning).lower()
    message = str(warning.get("message", "") if isinstance(warning, dict) else warning).lower()
    return "stale" in text or "veraltet" in message


def _warning_message(warning: Any) -> str:
    if isinstance(warning, dict):
        return str(warning.get("message") or warning.get("code") or warning)
    return str(warning)


def _low_battery_threshold() -> float:
    try:
        return float(os.getenv("ECOFLOW_LOW_BATTERY_THRESHOLD_PERCENT", "20"))
    except ValueError:
        return 20.0


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _entity_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    entity_id = item.get("entity_id", "-")
    state = item.get("state", "-")
    friendly_name = item.get("friendly_name")
    if friendly_name:
        return f"{entity_id} ({friendly_name}) - {state}"
    return f"{entity_id} - {state}"


def _count(data: dict[str, Any], key: str) -> int:
    try:
        return int(data.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _format_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unbekannt"
    if number == 0:
        number = 0.0
    return f"{number:.0f}"
