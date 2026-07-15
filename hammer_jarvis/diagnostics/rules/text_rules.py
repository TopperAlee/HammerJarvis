from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable

from hammer_jarvis.diagnostics.models import DiagnosticIssue, diagnostic_issue_id
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphNode


ENCODING_SUSPECT_PATTERN = re.compile(r"(Ãƒ|Ã„|Ãœ|Ã¶|Ã¼|Â|�)")


def run_text_rules(graph: EngineeringGraph, context: dict[str, Any] | None = None, project: Any | None = None) -> list[DiagnosticIssue]:
    issues: list[DiagnosticIssue] = []
    issues.extend(_empty_text(graph))
    issues.extend(_duplicate_text(graph))
    issues.extend(_imported_validator_issues(graph, "TEXT_TOO_LONG", "warning", "Text überschreitet Panelgrenze"))
    issues.extend(_imported_validator_issues(graph, "PLACEHOLDER_MISMATCH", "warning", "Placeholder unterscheiden sich"))
    issues.extend(_encoding_suspect(graph))
    issues.extend(_control_characters(graph))
    return issues


def text_rule_evaluators() -> list[tuple[str, str, str, str, list[str], Callable]]:
    return [
        ("TEXT_EMPTY", "Leerer Text", "TextResource enthält keinen sichtbaren Text.", "warning", ["TextResource"], _single(_empty_text)),
        ("TEXT_DUPLICATE", "Doppelter Text", "Identische normalisierte Texte wurden mehrfach gefunden.", "info", ["TextResource"], _single(_duplicate_text)),
        ("TEXT_TOO_LONG", "Text zu lang", "Importierte ProTool-Analyse meldet Panel-Längenproblem.", "warning", ["TextResource"], _single(lambda graph: _imported_validator_issues(graph, "TEXT_TOO_LONG", "warning", "Text überschreitet Panelgrenze"))),
        ("PLACEHOLDER_MISMATCH", "Placeholder-Abweichung", "Importierte ProTool-Analyse meldet abweichende Placeholder.", "warning", ["TextResource"], _single(lambda graph: _imported_validator_issues(graph, "PLACEHOLDER_MISMATCH", "warning", "Placeholder unterscheiden sich"))),
        ("ENCODING_SUSPECT", "Verdächtige Kodierung", "Text enthält typische Mojibake-Muster.", "warning", ["TextResource"], _single(_encoding_suspect)),
        ("CONTROL_CHARACTER", "Steuerzeichen", "Text enthält nicht erlaubte Steuerzeichen.", "warning", ["TextResource"], _single(_control_characters)),
    ]


def _single(func: Callable[[EngineeringGraph], list[DiagnosticIssue]]) -> Callable:
    def evaluator(graph: EngineeringGraph, context: dict[str, Any] | None = None, project: Any | None = None) -> list[DiagnosticIssue]:
        return func(graph)

    return evaluator


def _empty_text(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    issues = []
    for node in _text_nodes(graph):
        text = _text(node)
        if text.strip() == "":
            issues.append(_issue("TEXT_EMPTY", "warning", "Leerer Text", "Der HMI-Text ist leer oder besteht nur aus Leerzeichen.", node, {"text": text}, "Textinhalt im Quellprojekt prüfen."))
    return issues


def _duplicate_text(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    grouped: dict[str, list[GraphNode]] = defaultdict(list)
    for node in _text_nodes(graph):
        normalized = " ".join(_text(node).split()).casefold()
        if normalized:
            grouped[normalized].append(node)
    issues = []
    for normalized, nodes in grouped.items():
        if len(nodes) < 2:
            continue
        for node in nodes[1:]:
            issues.append(_issue("TEXT_DUPLICATE", "info", "Doppelter Text", "Dieser normalisierte Text kommt mehrfach vor.", node, {"normalized_text": normalized, "duplicates": [item.id for item in nodes]}, "Prüfen, ob die Dopplung fachlich gewollt ist."))
    return issues


def _imported_validator_issues(graph: EngineeringGraph, issue_type: str, severity: str, title: str) -> list[DiagnosticIssue]:
    issues = []
    for node in _text_nodes(graph):
        for imported_issue in node.metadata.get("issues") or []:
            if imported_issue.get("type") == issue_type:
                issues.append(_issue(issue_type, severity, title, str(imported_issue.get("type") or issue_type), node, dict(imported_issue), "ProTool-Analysehinweis im Quellprojekt prüfen."))
    return issues


def _encoding_suspect(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    issues = []
    for node in _text_nodes(graph):
        text = _text(node)
        match = ENCODING_SUSPECT_PATTERN.search(text)
        if match:
            issues.append(_issue("ENCODING_SUSPECT", "warning", "Verdächtige Kodierung", "Der Text enthält Zeichenfolgen, die auf Fehlkodierung hindeuten.", node, {"match": match.group(0), "text": text}, "Encoding der Exportdatei prüfen."))
    return issues


def _control_characters(graph: EngineeringGraph) -> list[DiagnosticIssue]:
    issues = []
    allowed = {"\n", "\r", "\t"}
    for node in _text_nodes(graph):
        text = _text(node)
        controls = [f"U+{ord(char):04X}" for char in text if ord(char) < 32 and char not in allowed]
        if controls:
            issues.append(_issue("CONTROL_CHARACTER", "warning", "Steuerzeichen im Text", "Der Text enthält nicht erlaubte Steuerzeichen.", node, {"control_characters": controls}, "Text auf unsichtbare Steuerzeichen prüfen."))
    return issues


def _text_nodes(graph: EngineeringGraph) -> list[GraphNode]:
    return [node for node in graph.nodes if node.type == "TextResource"]


def _text(node: GraphNode) -> str:
    return str(node.metadata.get("text", node.name) or "")


def _issue(rule_id: str, severity: str, title: str, description: str, node: GraphNode, evidence: dict[str, Any], recommendation: str) -> DiagnosticIssue:
    return DiagnosticIssue(
        id=_issue_id(rule_id, node.id, evidence),
        rule_id=rule_id,
        severity=severity,
        category="text",
        title=title,
        description=description,
        affected_object_id=node.id,
        affected_object_type=node.type,
        source_file=node.source_file,
        source_line=node.source_line,
        evidence=evidence,
        recommendation=recommendation,
    )


def _issue_id(rule_id: str, object_id: str, evidence: dict[str, Any]) -> str:
    return diagnostic_issue_id(rule_id, object_id, evidence)
