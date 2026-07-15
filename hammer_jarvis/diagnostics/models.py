from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SEVERITIES = ("info", "warning", "critical")
SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


def diagnostic_issue_id(rule_id: str, object_id: str | None, evidence: dict[str, Any]) -> str:
    canonical_evidence = json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(f"{rule_id}|{object_id}|{canonical_evidence}".encode("utf-8")).hexdigest()[:12]
    return f"{rule_id}:{digest}"


@dataclass
class DiagnosticIssue:
    id: str
    rule_id: str
    severity: str
    category: str
    title: str
    description: str
    affected_object_id: str | None
    affected_object_type: str | None
    source_file: str | None
    source_line: int | None
    evidence: dict[str, Any]
    recommendation: str
    read_only: bool = True


@dataclass
class DiagnosticReport:
    project_id: str | None
    generated_at: str
    issue_count: int
    info_count: int
    warning_count: int
    critical_count: int
    issues: list[DiagnosticIssue]
    executed_rules: list[str]
    statistics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_issues(
        cls,
        project_id: str | None,
        issues: list[DiagnosticIssue],
        *,
        executed_rules: list[str],
        statistics: dict[str, Any],
    ) -> "DiagnosticReport":
        return cls(
            project_id=project_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            issue_count=len(issues),
            info_count=sum(1 for issue in issues if issue.severity == "info"),
            warning_count=sum(1 for issue in issues if issue.severity == "warning"),
            critical_count=sum(1 for issue in issues if issue.severity == "critical"),
            issues=issues,
            executed_rules=executed_rules,
            statistics=statistics,
        )
