from __future__ import annotations

from dataclasses import asdict
from typing import Any

from hammer_jarvis.diagnostics.models import DiagnosticReport, SEVERITIES, SEVERITY_RANK
from hammer_jarvis.diagnostics.registry import DiagnosticRuleRegistry
from hammer_jarvis.engineering.graph import EngineeringGraph


class DiagnosticEngine:
    def __init__(self, registry: DiagnosticRuleRegistry | None = None) -> None:
        self.registry = registry or DiagnosticRuleRegistry()

    def run(
        self,
        graph: EngineeringGraph,
        context: dict[str, Any] | None = None,
        project: Any | None = None,
        *,
        project_id: str | None = None,
        include_categories: list[str] | None = None,
        severity_min: str = "info",
    ) -> DiagnosticReport:
        categories = set(include_categories) if include_categories else None
        issues = []
        executed_rules = []
        failed_rules = []

        for rule in self.registry.active(categories):
            try:
                issues.extend(rule.evaluator(graph, context, project))
                executed_rules.append(rule.rule_id)
            except Exception:
                failed_rules.append(rule.rule_id)

        issues = _filter_severity(issues, severity_min)
        issues.sort(key=lambda issue: (SEVERITY_RANK.get(issue.severity, 99), issue.category, issue.rule_id, issue.id))
        return DiagnosticReport.from_issues(
            project_id,
            issues,
            executed_rules=executed_rules,
            statistics={
                "failed_rule_count": len(failed_rules),
                "failed_rules": failed_rules,
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
                "read_only": True,
            },
        )


class DiagnosticReportStore:
    def __init__(self) -> None:
        self._latest: DiagnosticReport | None = None

    def save(self, report: DiagnosticReport) -> None:
        self._latest = report

    def get_latest(self) -> DiagnosticReport | None:
        return self._latest

    def clear(self) -> None:
        self._latest = None


def report_to_dict(report: DiagnosticReport) -> dict[str, Any]:
    return asdict(report)


def validate_severity(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in SEVERITIES:
        raise ValueError(f"Invalid severity: {value}")
    return normalized


def _filter_severity(issues, severity_min: str):
    threshold = SEVERITY_RANK[validate_severity(severity_min)]
    return [issue for issue in issues if SEVERITY_RANK.get(issue.severity, 99) <= threshold]
