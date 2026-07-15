from typing import Any

from pydantic import BaseModel, Field

from hammer_jarvis.intent.capabilities import CapabilityRegistry
from hammer_jarvis.intent.models import ContextState


class Recommendation(BaseModel):
    id: str
    title: str
    message: str
    severity: str = "info"
    source: str
    intent: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True


class RecommendationEngine:
    """Builds deterministic read-only recommendations from current assistant context."""

    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
        knowledge_empty: bool = False,
        voice_ready: bool = True,
    ) -> None:
        self._capabilities = capability_registry or CapabilityRegistry()
        self._knowledge_empty = knowledge_empty
        self._voice_ready = voice_ready

    def build(self, context: ContextState) -> list[Recommendation]:
        recommendations: list[Recommendation] = []

        if not context.active_project_id:
            recommendations.append(
                Recommendation(
                    id="engineering.open_project",
                    title="Projekt öffnen",
                    message="Es ist kein Engineering-Projekt aktiv. Öffne ein Projekt, damit Jarvis den Arbeitskontext nutzen kann.",
                    severity="info",
                    source="engineering",
                    intent="engineering.project.open",
                    arguments={},
                )
            )
        elif context.active_workspace == "engineering":
            recommendations.append(
                Recommendation(
                    id="engineering.analyze_project_files",
                    title="Projektdateien analysieren",
                    message=f"Das Projekt {context.active_project_name or context.active_project_id} ist aktiv. Als nächster Schritt können die Projektdateien read-only analysiert werden.",
                    severity="info",
                    source="engineering",
                    intent="engineering.project.search",
                    arguments={"project_id": context.active_project_id},
                )
            )

        if _is_protool_csv_context(context):
            recommendations.append(
                Recommendation(
                    id="engineering.protool_analyze_active_csv",
                    title="ProTool Analyse starten",
                    message=f"{context.active_file or 'Die aktive CSV-Datei'} sieht nach einer ProTool-CSV aus. Eine read-only Analyse kann Textlängen, Zeilen und Placeholder prüfen.",
                    severity="info",
                    source="engineering",
                    intent="engineering.protool.analyze",
                    arguments={"file": context.active_file, "panel": context.active_panel},
                )
            )

        if context.current_task == "protool_analysis_has_issues":
            recommendations.append(
                Recommendation(
                    id="engineering.protool_check_panel_preview",
                    title="Panel-Vorschau prüfen",
                    message="Die letzte ProTool-Analyse hat Hinweise gefunden. Prüfe die Panel-Vorschau, bevor du Texte außerhalb von Jarvis bearbeitest.",
                    severity="warning",
                    source="engineering",
                    intent="engineering.panel.preview",
                    arguments={"file": context.active_file, "panel": context.active_panel},
                )
            )

        if context.current_task == "protool_texts_imported":
            recommendations.append(
                Recommendation(
                    id="engineering.protool_texts_available",
                    title="ProTool Texte im Graph verfügbar",
                    message="Die ProTool-Texte wurden als Engineering-Objekte importiert und können nun über den Object Graph genutzt werden.",
                    severity="info",
                    source="engineering",
                    intent="engineering.panel.preview",
                    arguments={"file": context.active_file, "panel": context.active_panel},
                )
            )

        if context.current_task == "engineering.diagnostics":
            critical = context.diagnostic_critical_count or 0
            warnings = context.diagnostic_warning_count or 0
            total = context.diagnostic_issue_count or 0
            if critical > 0:
                recommendations.append(
                    Recommendation(
                        id="engineering.diagnostics_review_critical",
                        title="Kritische Engineering-Probleme prüfen",
                        message=f"Die letzte Diagnose hat {critical} kritische Auffälligkeit(en) gefunden.",
                        severity="critical",
                        source="engineering",
                        intent="engineering.diagnostics.run",
                        arguments={},
                    )
                )
            elif warnings > 0:
                recommendations.append(
                    Recommendation(
                        id="engineering.diagnostics_review_warnings",
                        title="Engineering-Warnungen prüfen",
                        message=f"Die letzte Diagnose hat {warnings} Warnung(en) gefunden.",
                        severity="warning",
                        source="engineering",
                        intent="engineering.diagnostics.run",
                        arguments={},
                    )
                )
            elif total == 0:
                recommendations.append(
                    Recommendation(
                        id="engineering.diagnostics_no_issues",
                        title="Keine diagnostischen Auffälligkeiten gefunden",
                        message="Die letzte Engineering-Diagnose hat keine Issues gemeldet.",
                        severity="info",
                        source="engineering",
                        intent="engineering.diagnostics.run",
                        arguments={},
                    )
                )

        if context.current_task == "engineering.understanding":
            recommendations.append(
                Recommendation(
                    id="engineering.understanding_model_built",
                    title="Engineering-Modell erfolgreich aufgebaut",
                    message="Das lokale Engineering-Modell wurde aus vorhandenen Graph-, Diagnose-, Dokument- und Knowledge-Daten aufgebaut.",
                    severity="info",
                    source="engineering",
                    intent="engineering.understanding.build",
                    arguments={},
                )
            )

        if self._knowledge_empty:
            recommendations.append(
                Recommendation(
                    id="knowledge.index_documents",
                    title="Dokumente indexieren",
                    message="Der Wissensspeicher ist leer. Indexiere lokale Dokumente, damit Jarvis projektbezogene Quellen finden kann.",
                    severity="info",
                    source="knowledge",
                    intent="knowledge.search",
                    arguments={},
                )
            )

        if not self._voice_ready and _capability_exists(self._capabilities, "assistant.status"):
            recommendations.append(
                Recommendation(
                    id="voice.check_status",
                    title="Voice-Status prüfen",
                    message="Voice ist aktuell nicht bereit. Prüfe den lokalen Sprachstatus, wenn du Jarvis per Sprache nutzen willst.",
                    severity="warning",
                    source="voice",
                    intent="assistant.status",
                    arguments={},
                )
            )

        return recommendations


def _is_protool_csv_context(context: ContextState) -> bool:
    file_name = (context.active_file or "").lower()
    file_type = (context.active_file_type or "").upper()
    return file_name.endswith(".csv") and (
        "PROTOOL" in file_type
        or file_type in {"MESSAGE_TEXT", "ALARM_TEXT", "INFO_TEXT", "TEXT_LIST", "RECIPE", "VARIABLES"}
        or file_name in {"messagetext.csv", "alarmtext.csv", "infohelptext.csv", "textlist.csv", "recipetext.csv", "variables.csv"}
    )


def _capability_exists(registry: CapabilityRegistry, capability_id: str) -> bool:
    return registry.get(capability_id) is not None
