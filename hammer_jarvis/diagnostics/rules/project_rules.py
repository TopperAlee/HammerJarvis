from __future__ import annotations

from typing import Any, Callable

from hammer_jarvis.diagnostics.models import DiagnosticIssue, diagnostic_issue_id
from hammer_jarvis.engineering.classifier.protool import ProjectFileType, ProToolClassifier
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphNode


PROTOOL_TEXT_FILE_TYPES = {
    ProjectFileType.MESSAGE_TEXT,
    ProjectFileType.ALARM_TEXT,
    ProjectFileType.INFO_TEXT,
    ProjectFileType.TEXT_LIST,
    ProjectFileType.RECIPE,
}


def run_project_rules(graph: EngineeringGraph, context: dict[str, Any] | None = None, project: Any | None = None) -> list[DiagnosticIssue]:
    issues: list[DiagnosticIssue] = []
    issues.extend(_project_no_files(graph))
    issues.extend(_project_unknown_files(graph))
    issues.extend(_project_no_text_resources(graph))
    issues.extend(_project_panel_missing(graph))
    return issues


def project_rule_evaluators() -> list[tuple[str, str, str, str, list[str], Callable]]:
    return [
        ("PROJECT_NO_FILES", "Projekt ohne Dateien", "Projekt enthält keine ProjectFile-Knoten.", "warning", ["Project"], _single(_project_no_files)),
        ("PROJECT_UNKNOWN_FILES", "Unbekannte Dateien", "Projekt enthält unbekannte Dateitypen.", "info", ["ProjectFile"], _single(_project_unknown_files)),
        ("PROJECT_NO_TEXT_RESOURCES", "Keine TextResources", "ProTool-Projekt erkannt, aber keine TextResource importiert.", "warning", ["Project"], _single(_project_no_text_resources)),
        ("PROJECT_PANEL_MISSING", "Panel fehlt", "TextResources haben keinen Panelkontext.", "warning", ["TextResource"], _single(_project_panel_missing)),
    ]


def _single(func: Callable[[EngineeringGraph], list[DiagnosticIssue]]) -> Callable:
    def evaluator(graph: EngineeringGraph, context: dict[str, Any] | None = None, project: Any | None = None) -> list[DiagnosticIssue]:
        return func(graph)

    return evaluator


def _project_no_files(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    if any(node.type == "ProjectFile" for node in graph.nodes):
        return []
    project = next((node for node in graph.nodes if node.type == "Project"), None)
    return [_issue("PROJECT_NO_FILES", "warning", "Projekt ohne Dateien", "Das Projekt enthält keine ProjectFile-Knoten.", project, {"project_nodes": [node.id for node in graph.nodes if node.type == "Project"]}, "Project Explorer Import prüfen.")]


def _project_unknown_files(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    issues = []
    for node in graph.nodes:
        if node.type != "ProjectFile":
            continue
        file_type = str(node.metadata.get("file_type") or node.metadata.get("type") or node.metadata.get("kind") or "").upper()
        if file_type == "UNKNOWN":
            issues.append(_issue("PROJECT_UNKNOWN_FILES", "info", "Unbekannter Dateityp", "Eine ProjectFile konnte nicht klassifiziert werden.", node, {"file_type": file_type}, "Dateityp-Klassifizierung prüfen."))
    return issues


def _project_no_text_resources(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    classifier = ProToolClassifier()
    has_protool_file = any(
        node.type == "ProjectFile" and classifier.classify(node.name) in PROTOOL_TEXT_FILE_TYPES
        for node in graph.nodes
    )
    has_text = any(node.type == "TextResource" for node in graph.nodes)
    if not has_protool_file or has_text:
        return []
    project = next((node for node in graph.nodes if node.type == "Project"), None)
    return [_issue("PROJECT_NO_TEXT_RESOURCES", "warning", "Keine TextResources importiert", "ProTool-Dateien sind vorhanden, aber keine TextResource-Knoten.", project, {"protool_files_detected": True}, "ProTool Importer für Textdateien ausführen.")]


def _project_panel_missing(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    return [
        _issue("PROJECT_PANEL_MISSING", "warning", "Panelkontext fehlt", "TextResource besitzt keinen Panelkontext.", node, {"panel": node.metadata.get("panel")}, "Panel beim Import oder bei der Analyse angeben.")
        for node in graph.nodes
        if node.type == "TextResource" and not node.metadata.get("panel")
    ]


def _issue(rule_id: str, severity: str, title: str, description: str, node: GraphNode | None, evidence: dict[str, Any], recommendation: str) -> DiagnosticIssue:
    object_id = node.id if node else None
    return DiagnosticIssue(
        id=diagnostic_issue_id(rule_id, object_id, evidence),
        rule_id=rule_id,
        severity=severity,
        category="project",
        title=title,
        description=description,
        affected_object_id=object_id,
        affected_object_type=node.type if node else None,
        source_file=node.source_file if node else None,
        source_line=node.source_line if node else None,
        evidence=evidence,
        recommendation=recommendation,
    )
