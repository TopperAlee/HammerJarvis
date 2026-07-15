from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from hammer_jarvis.diagnostics.models import DiagnosticIssue, diagnostic_issue_id
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphNode


def run_graph_rules(graph: EngineeringGraph, context: dict[str, Any] | None = None, project: Any | None = None) -> list[DiagnosticIssue]:
    issues: list[DiagnosticIssue] = []
    issues.extend(_broken_edges(graph))
    issues.extend(_orphan_nodes(graph))
    issues.extend(_duplicate_node_ids(graph))
    issues.extend(_text_without_project_file(graph))
    return issues


def graph_rule_evaluators() -> list[tuple[str, str, str, str, list[str], Callable]]:
    return [
        ("GRAPH_ORPHAN_NODE", "Verwaister Knoten", "Knoten besitzt keine sinnvolle Beziehung.", "info", ["*"], _single(_orphan_nodes)),
        ("GRAPH_BROKEN_EDGE", "Kaputte Beziehung", "Edge verweist auf fehlenden Knoten.", "critical", ["*"], _single(_broken_edges)),
        ("DUPLICATE_NODE_ID", "Doppelte Node-ID", "Graph enthält doppelte Knoten-IDs.", "critical", ["*"], _single(_duplicate_node_ids)),
        ("TEXT_WITHOUT_PROJECT_FILE", "Text ohne ProjectFile", "TextResource wird von keiner ProjectFile definiert.", "warning", ["TextResource"], _single(_text_without_project_file)),
    ]


def _single(func: Callable[[EngineeringGraph], list[DiagnosticIssue]]) -> Callable:
    def evaluator(graph: EngineeringGraph, context: dict[str, Any] | None = None, project: Any | None = None) -> list[DiagnosticIssue]:
        return func(graph)

    return evaluator


def _broken_edges(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    node_ids = {node.id for node in graph.nodes}
    issues = []
    for edge in graph.edges:
        missing = []
        if edge.source_id not in node_ids:
            missing.append("source_id")
        if edge.target_id not in node_ids:
            missing.append("target_id")
        if missing:
            issues.append(_issue("GRAPH_BROKEN_EDGE", "critical", "Kaputte Beziehung", "Eine Graph-Beziehung verweist auf fehlende Knoten.", None, {"edge": {"source_id": edge.source_id, "target_id": edge.target_id, "type": edge.type}, "missing": missing}, "Graph-Import prüfen."))
    return issues


def _orphan_nodes(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    connected = {edge.source_id for edge in graph.edges} | {edge.target_id for edge in graph.edges}
    return [
        _issue("GRAPH_ORPHAN_NODE", "info", "Verwaister Knoten", "Der Knoten hat keine ein- oder ausgehende Beziehung.", node, {"node_id": node.id}, "Importpfad oder Klassifizierung prüfen.")
        for node in graph.nodes
        if node.type != "Project" and node.id not in connected
    ]


def _duplicate_node_ids(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    counts = Counter(node.id for node in graph.nodes)
    issues = []
    for node_id, count in counts.items():
        if count > 1:
            node = next(node for node in graph.nodes if node.id == node_id)
            issues.append(_issue("DUPLICATE_NODE_ID", "critical", "Doppelte Node-ID", "Eine Node-ID kommt mehrfach vor.", node, {"node_id": node_id, "count": count}, "Stabile ID-Erzeugung des Importers prüfen."))
    return issues


def _text_without_project_file(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    project_file_ids = {node.id for node in graph.nodes if node.type == "ProjectFile"}
    defined_text_ids = {edge.target_id for edge in graph.edges if edge.type == "DEFINES" and edge.source_id in project_file_ids}
    return [
        _issue("TEXT_WITHOUT_PROJECT_FILE", "warning", "Text ohne ProjectFile", "TextResource besitzt keine DEFINES-Beziehung von einer ProjectFile.", node, {"text_resource_id": node.id}, "Importer-Beziehungen prüfen.")
        for node in graph.nodes
        if node.type == "TextResource" and node.id not in defined_text_ids
    ]


def _issue(rule_id: str, severity: str, title: str, description: str, node: GraphNode | None, evidence: dict[str, Any], recommendation: str) -> DiagnosticIssue:
    object_id = node.id if node else None
    return DiagnosticIssue(
        id=diagnostic_issue_id(rule_id, object_id, evidence),
        rule_id=rule_id,
        severity=severity,
        category="graph",
        title=title,
        description=description,
        affected_object_id=object_id,
        affected_object_type=node.type if node else None,
        source_file=node.source_file if node else None,
        source_line=node.source_line if node else None,
        evidence=evidence,
        recommendation=recommendation,
    )
