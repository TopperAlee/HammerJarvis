import os
from typing import Any

from app.agent.permissions import ActionRisk
from app.assistant.actions.pending_action_store import PendingActionStore, pending_action_store


class ActionPlanner:
    """Create safe pending follow-up actions from existing tool and mission results."""

    def __init__(self, store: PendingActionStore | None = None) -> None:
        self.store = store or pending_action_store

    def create_actions_from_mission(self, mission_result: dict[str, Any]) -> list[dict[str, Any]]:
        """Plan non-destructive next actions for Hauscheck, Tagesstatus and Energiecheck."""
        mission = str(mission_result.get("mission") or "chat")
        tool_results = mission_result.get("tool_results", {})
        actions: list[dict[str, Any]] = []
        if mission in {"home_check", "daily_briefing", "energy_check"}:
            actions.extend(self._low_battery_actions(tool_results))
        if mission in {"home_check", "daily_briefing"}:
            actions.extend(self._home_assistant_actions(tool_results, mission_result))
        if mission in {"home_check", "daily_briefing", "energy_check"}:
            actions.extend(self._ecoflow_actions(tool_results, mission_result))
        return [self.store.create_action(action) for action in actions[:5]]

    def create_actions_from_file_search(self, search_result: dict[str, Any]) -> list[dict[str, Any]]:
        """Suggest read/export follow-ups for local search results."""
        if not search_result.get("files"):
            return []
        actions = [
            {
                "title": "Besten Treffer öffnen",
                "description": "Öffnet den besten Treffer aus der letzten lokalen Dateisuche.",
                "tool_name": "file_open_best_match",
                "arguments": {},
                "risk": ActionRisk.GREEN,
                "source": "file_search",
            },
            {
                "title": "Suchergebnisse als Excel exportieren",
                "description": "Erstellt eine lokale Excel-Übersicht der gefundenen Dateien.",
                "tool_name": "file_create_excel",
                "arguments": _file_index_arguments(search_result),
                "risk": ActionRisk.GREEN,
                "source": "file_search",
            },
        ]
        return [self.store.create_action(action) for action in actions]

    def create_actions_from_web_research(self, research_result: dict[str, Any]) -> list[dict[str, Any]]:
        """Suggest saving a source-based web research report."""
        if not research_result.get("sources"):
            return []
        return [
            self.store.create_action(
                {
                    "title": "Recherchebericht als Markdown speichern",
                    "description": "Speichert die gefundenen Quellen als lokalen Markdown-Bericht.",
                    "tool_name": "file_create_markdown",
                    "arguments": {
                        "title": "Recherchebericht",
                        "filename": "recherchebericht.md",
                        "content": _web_report_content(research_result),
                    },
                    "risk": ActionRisk.GREEN,
                    "source": "web_research",
                }
            )
        ]

    def _home_assistant_actions(self, tool_results: dict[str, Any], mission_result: dict[str, Any]) -> list[dict[str, Any]]:
        problems = tool_results.get("home_assistant_get_problems", {})
        actions = [
            {
                "title": "Diagnosebericht erstellen",
                "description": "Speichert den aktuellen Hauscheck als lokalen Markdown-Bericht.",
                "tool_name": "hauscheck_diagnostic_report",
                "arguments": {},
                "risk": ActionRisk.GREEN,
                "source": "hauscheck",
            }
        ]
        if _has_backup_warning(problems):
            actions.append(
                {
                    "title": "Home-Assistant-Backup-Warnungen analysieren",
                    "description": "Backup-Sensoren erneut prüfen und Diagnose anzeigen.",
                    "tool_name": "home_assistant_get_problems",
                    "arguments": {},
                    "risk": ActionRisk.GREEN,
                    "source": "hauscheck",
                }
            )
        return actions

    def _ecoflow_actions(self, tool_results: dict[str, Any], mission_result: dict[str, Any]) -> list[dict[str, Any]]:
        ecoflow = tool_results.get("ecoflow_energy_overview", {})
        actions: list[dict[str, Any]] = []
        if ecoflow.get("warnings", []):
            actions.append(
                {
                    "title": "EcoFlow-Diagnosebericht erstellen",
                    "description": "Speichert die aktuelle EcoFlow-Diagnose als lokalen Markdown-Bericht.",
                    "tool_name": "file_create_markdown",
                    "arguments": {
                        "title": "EcoFlow Diagnosebericht",
                        "filename": "ecoflow_diagnosebericht.md",
                        "content": _mission_report_content(mission_result),
                    },
                    "risk": ActionRisk.GREEN,
                    "source": "hauscheck",
                }
            )
        return actions

    def _low_battery_actions(self, tool_results: dict[str, Any]) -> list[dict[str, Any]]:
        ecoflow = tool_results.get("ecoflow_energy_overview", {})
        soc = _soc_percent(ecoflow)
        if soc is None or soc > _low_battery_threshold():
            return []
        return [
            {
                "title": "EcoFlow-Batterie kritisch niedrig prüfen",
                "description": (
                    "Die EcoFlow-Batterie liegt unter dem Schwellwert. Jarvis kann sichere "
                    "Energiesparmaßnahmen vorschlagen, schaltet aber nichts automatisch."
                ),
                "tool_name": "energy_saving_recommendations",
                "arguments": {"soc_percent": soc, "source": "ecoflow"},
                "risk": ActionRisk.YELLOW,
                "source": "hauscheck",
                "requires_confirmation": True,
            }
        ]


def _has_backup_warning(problems: dict[str, Any]) -> bool:
    items = [*(problems.get("critical", []) or []), *(problems.get("warning", []) or []), *(problems.get("informational", []) or [])]
    return any("backup" in str(item).lower() for item in items)


def _soc_percent(ecoflow: dict[str, Any]) -> float | None:
    value = ecoflow.get("soc_percent")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _low_battery_threshold() -> float:
    try:
        return float(os.getenv("ECOFLOW_LOW_BATTERY_THRESHOLD_PERCENT", "20"))
    except ValueError:
        return 20.0


def _mission_report_content(mission_result: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Mission: {mission_result.get('mission', '-')}",
            "",
            "Antwort:",
            str(mission_result.get("answer", "")),
            "",
            "Hinweis: Dieser Bericht wurde lokal aus bereits vorhandenen Hammer-Jarvis-Daten erstellt.",
        ]
    )


def _file_index_arguments(search_result: dict[str, Any]) -> dict[str, Any]:
    rows = [
        [
            file.get("name", ""),
            file.get("path", ""),
            file.get("extension", ""),
            file.get("size_bytes", ""),
            file.get("modified_at", ""),
            ", ".join(file.get("match_sources", [])),
            file.get("score", ""),
        ]
        for file in search_result.get("files", [])
    ]
    return {
        "title": "Suchergebnisse",
        "filename": "suchergebnisse.xlsx",
        "sheets": [
            {
                "name": "Suchergebnisse",
                "headers": ["Dateiname", "Pfad", "Typ", "Größe", "Geändert am", "Trefferart", "Score"],
                "rows": rows,
            }
        ],
    }


def _web_report_content(research_result: dict[str, Any]) -> str:
    lines = ["## Recherchebericht", "", str(research_result.get("summary") or research_result.get("message") or ""), "", "## Quellen"]
    for source in research_result.get("sources", []):
        lines.append(f"- {source.get('title', 'Quelle')}: {source.get('url', '')}")
    return "\n".join(lines)
