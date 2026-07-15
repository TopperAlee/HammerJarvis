from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from hammer_jarvis.diagnostics.models import DiagnosticIssue
from hammer_jarvis.engineering.graph import EngineeringGraph


RuleEvaluator = Callable[[EngineeringGraph, dict[str, Any] | None, Any | None], list[DiagnosticIssue]]


@dataclass
class DiagnosticRule:
    rule_id: str
    name: str
    category: str
    description: str
    default_severity: str
    applicable_node_types: list[str]
    enabled: bool
    evaluator: RuleEvaluator


class DiagnosticRuleRegistry:
    def __init__(self, rules: list[DiagnosticRule] | None = None) -> None:
        self._rules = rules if rules is not None else _default_rules()

    def list(self) -> list[DiagnosticRule]:
        return list(self._rules)

    def active(self, categories: set[str] | None = None) -> list[DiagnosticRule]:
        return [
            rule
            for rule in self._rules
            if rule.enabled and (categories is None or rule.category in categories)
        ]

    def register(self, rule: DiagnosticRule) -> None:
        self._rules.append(rule)


def _default_rules() -> list[DiagnosticRule]:
    from hammer_jarvis.diagnostics.rules.graph_rules import graph_rule_evaluators
    from hammer_jarvis.diagnostics.rules.project_rules import project_rule_evaluators
    from hammer_jarvis.diagnostics.rules.text_rules import text_rule_evaluators

    rules: list[DiagnosticRule] = []
    for rule_id, name, description, severity, node_types, evaluator in text_rule_evaluators():
        rules.append(DiagnosticRule(rule_id, name, "text", description, severity, node_types, True, evaluator))
    for rule_id, name, description, severity, node_types, evaluator in graph_rule_evaluators():
        rules.append(DiagnosticRule(rule_id, name, "graph", description, severity, node_types, True, evaluator))
    for rule_id, name, description, severity, node_types, evaluator in project_rule_evaluators():
        rules.append(DiagnosticRule(rule_id, name, "project", description, severity, node_types, True, evaluator))
    return rules
