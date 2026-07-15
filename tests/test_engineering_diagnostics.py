from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from hammer_jarvis.diagnostics.engine import DiagnosticEngine, DiagnosticReportStore
from hammer_jarvis.diagnostics.models import DiagnosticIssue, DiagnosticReport
from hammer_jarvis.diagnostics.registry import DiagnosticRule, DiagnosticRuleRegistry
from hammer_jarvis.diagnostics.rules.graph_rules import run_graph_rules
from hammer_jarvis.diagnostics.rules.project_rules import run_project_rules
from hammer_jarvis.diagnostics.rules.text_rules import run_text_rules
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphEdge, GraphNode
from hammer_jarvis.intent.capabilities import CapabilityRegistry
from hammer_jarvis.intent.context import ContextStore
from hammer_jarvis.intent.parser import IntentParser
from hammer_jarvis.intent.recommendations import RecommendationEngine


client = TestClient(app)


def _text_node(
    node_id: str,
    text: str,
    *,
    source_file: str = "MessageText.csv",
    source_line: int = 1,
    panel: str | None = "OP7",
    issues: list[dict] | None = None,
) -> GraphNode:
    return GraphNode(
        id=node_id,
        type="TextResource",
        name=text or "Leertext",
        source_file=source_file,
        source_line=source_line,
        metadata={"text": text, "panel": panel, "issues": issues or []},
    )


def test_diagnostic_issue_is_serializable() -> None:
    issue = DiagnosticIssue(
        id="issue-1",
        rule_id="TEXT_EMPTY",
        severity="warning",
        category="text",
        title="Leerer Text",
        description="Text ist leer.",
        affected_object_id="text:1",
        affected_object_type="TextResource",
        source_file="MessageText.csv",
        source_line=2,
        evidence={"text": ""},
        recommendation="Text prüfen.",
    )

    payload = asdict(issue)

    assert payload["read_only"] is True
    assert payload["evidence"]["text"] == ""


def test_diagnostic_report_counts_are_correct() -> None:
    issues = [
        DiagnosticIssue("i1", "A", "info", "text", "Info", "Info", None, None, None, None, {}, "Prüfen."),
        DiagnosticIssue("i2", "B", "warning", "graph", "Warnung", "Warnung", None, None, None, None, {}, "Prüfen."),
        DiagnosticIssue("i3", "C", "critical", "project", "Kritisch", "Kritisch", None, None, None, None, {}, "Prüfen."),
    ]

    report = DiagnosticReport.from_issues("demo-project", issues, executed_rules=["A", "B", "C"], statistics={})

    assert report.issue_count == 3
    assert report.info_count == 1
    assert report.warning_count == 1
    assert report.critical_count == 1


def test_rule_registry_contains_expected_rules() -> None:
    rules = DiagnosticRuleRegistry().list()
    rule_ids = {rule.rule_id for rule in rules}

    assert "TEXT_EMPTY" in rule_ids
    assert "GRAPH_BROKEN_EDGE" in rule_ids
    assert "PROJECT_NO_FILES" in rule_ids
    assert all(rule.enabled for rule in rules)


def test_text_rules_detect_empty_duplicate_encoding_and_imported_validator_issues() -> None:
    graph = EngineeringGraph(
        nodes=[
            _text_node("text:empty", "   ", source_line=1),
            _text_node("text:one", "Hydraulik bereit", source_line=2),
            _text_node("text:two", "  Hydraulik   bereit ", source_line=3),
            _text_node("text:encoding", "RÃƒÂ¼ckzug", source_line=4),
            _text_node("text:control", "Alarm\x07Text", source_line=5),
            _text_node(
                "text:long",
                "Sehr langer Text",
                source_line=6,
                issues=[{"type": "TEXT_TOO_LONG", "max": 20, "actual": 32, "text": "Sehr langer Text"}],
            ),
        ]
    )

    issues = run_text_rules(graph)
    rule_ids = {issue.rule_id for issue in issues}

    assert {"TEXT_EMPTY", "TEXT_DUPLICATE", "ENCODING_SUSPECT", "CONTROL_CHARACTER", "TEXT_TOO_LONG"}.issubset(rule_ids)


def test_graph_rules_detect_broken_edge_orphan_text_and_duplicate_node_id() -> None:
    project = GraphNode("project:1", "Project", "Projekt", None)
    text = _text_node("text:orphan", "Alarm")
    duplicate_a = GraphNode("dup", "ProjectFile", "A.csv", "A.csv")
    duplicate_b = GraphNode("dup", "ProjectFile", "B.csv", "B.csv")
    graph = EngineeringGraph(
        nodes=[project, text, duplicate_a, duplicate_b],
        edges=[GraphEdge("project:1", "missing:file", "CONTAINS")],
    )

    issues = run_graph_rules(graph)
    rule_ids = {issue.rule_id for issue in issues}

    assert "GRAPH_BROKEN_EDGE" in rule_ids
    assert "GRAPH_ORPHAN_NODE" in rule_ids
    assert "DUPLICATE_NODE_ID" in rule_ids
    assert "TEXT_WITHOUT_PROJECT_FILE" in rule_ids


def test_project_rules_detect_empty_project_unknown_files_and_missing_text_resources() -> None:
    empty_project = EngineeringGraph(nodes=[GraphNode("project:empty", "Project", "Leer", None)])
    protool_without_text = EngineeringGraph(
        nodes=[
            GraphNode("project:1", "Project", "Projekt", None),
            GraphNode("file:1", "ProjectFile", "MessageText.csv", "MessageText.csv", metadata={"file_type": "UNKNOWN"}),
        ],
        edges=[GraphEdge("project:1", "file:1", "CONTAINS")],
    )
    missing_panel = EngineeringGraph(
        nodes=[
            GraphNode("project:2", "Project", "Projekt", None),
            GraphNode("file:2", "ProjectFile", "MessageText.csv", "MessageText.csv"),
            _text_node("text:no-panel", "Alarm", panel=None),
        ],
        edges=[
            GraphEdge("project:2", "file:2", "CONTAINS"),
            GraphEdge("file:2", "text:no-panel", "DEFINES"),
        ],
    )

    assert any(issue.rule_id == "PROJECT_NO_FILES" for issue in run_project_rules(empty_project))
    ids = {issue.rule_id for issue in run_project_rules(protool_without_text)}
    assert {"PROJECT_UNKNOWN_FILES", "PROJECT_NO_TEXT_RESOURCES"}.issubset(ids)
    assert any(issue.rule_id == "PROJECT_PANEL_MISSING" for issue in run_project_rules(missing_panel))


def test_project_rules_do_not_require_text_resources_for_variables_only_project() -> None:
    variables_only = EngineeringGraph(
        nodes=[
            GraphNode("project:variables", "Project", "Projekt", None),
            GraphNode("file:variables", "ProjectFile", "Variables.csv", "Variables.csv"),
        ],
        edges=[GraphEdge("project:variables", "file:variables", "CONTAINS")],
    )

    assert not any(issue.rule_id == "PROJECT_NO_TEXT_RESOURCES" for issue in run_project_rules(variables_only))


def test_diagnostic_issue_ids_use_canonical_evidence_order() -> None:
    first = _text_node("text:ordered", "Text", issues=[{"type": "TEXT_TOO_LONG", "max": 20, "actual": 32}])
    second = _text_node("text:ordered", "Text", issues=[{"actual": 32, "max": 20, "type": "TEXT_TOO_LONG"}])

    first_issue = next(issue for issue in run_text_rules(EngineeringGraph(nodes=[first])) if issue.rule_id == "TEXT_TOO_LONG")
    second_issue = next(issue for issue in run_text_rules(EngineeringGraph(nodes=[second])) if issue.rule_id == "TEXT_TOO_LONG")

    assert first_issue.id == second_issue.id


def test_diagnostic_engine_runs_multiple_rules_and_sorts_by_severity() -> None:
    graph = EngineeringGraph(
        nodes=[GraphNode("project:1", "Project", "Projekt", None), _text_node("text:empty", "")],
        edges=[GraphEdge("project:1", "missing", "CONTAINS")],
    )

    report = DiagnosticEngine().run(graph, project_id="demo-project")

    assert report.issue_count >= 2
    assert report.executed_rules
    assert report.issues[0].severity in {"critical", "warning", "info"}
    assert report.statistics["failed_rule_count"] == 0


def test_diagnostic_engine_rule_error_does_not_abort_report() -> None:
    def failing_rule(graph, context=None, project=None):
        raise RuntimeError("internal detail")

    registry = DiagnosticRuleRegistry(
        rules=[
            DiagnosticRule("BROKEN_RULE", "Broken", "text", "Fails", "warning", ["TextResource"], True, failing_rule),
        ]
    )

    report = DiagnosticEngine(registry=registry).run(EngineeringGraph(), project_id="demo-project")

    assert report.issue_count == 0
    assert report.statistics["failed_rule_count"] == 1
    assert "internal detail" not in str(asdict(report))


def test_diagnostic_report_store_saves_latest_report() -> None:
    store = DiagnosticReportStore()
    report = DiagnosticReport.from_issues("demo-project", [], executed_rules=[], statistics={})

    store.save(report)

    assert store.get_latest() == report
    store.clear()
    assert store.get_latest() is None


def test_engineering_diagnostics_api_endpoints() -> None:
    run_response = client.post(
        "/assistant/engineering/diagnostics/run",
        json={"project_id": "demo-project", "include_categories": ["text", "graph", "project"], "severity_min": "info"},
    )
    rules_response = client.get("/assistant/engineering/diagnostics/rules")
    latest_response = client.get("/assistant/engineering/diagnostics/latest")

    assert run_response.status_code == 200
    assert run_response.json()["project_id"] == "demo-project"
    assert rules_response.status_code == 200
    assert any(rule["rule_id"] == "TEXT_EMPTY" for rule in rules_response.json())
    assert latest_response.status_code == 200
    assert latest_response.json()["project_id"] == "demo-project"


def test_engineering_diagnostics_api_validation_and_issue_lookup() -> None:
    assert client.post("/assistant/engineering/diagnostics/run", json={"project_id": "missing"}).status_code == 404
    assert client.post("/assistant/engineering/diagnostics/run", json={"include_categories": ["invalid"]}).status_code == 400
    assert client.post("/assistant/engineering/diagnostics/run", json={"severity_min": "urgent"}).status_code == 400

    report = client.post("/assistant/engineering/diagnostics/run", json={"project_id": "demo-project"}).json()
    if report["issues"]:
        issue_id = report["issues"][0]["id"]
        issue_response = client.get(f"/assistant/engineering/diagnostics/issues/{issue_id}")
        assert issue_response.status_code == 200
        assert issue_response.json()["id"] == issue_id
    assert client.get("/assistant/engineering/diagnostics/issues/does-not-exist").status_code == 404


def test_intent_capability_and_recommendations_support_engineering_diagnostics() -> None:
    intent = IntentParser().parse_text("diagnose starten")
    capability = CapabilityRegistry().get("engineering.diagnostics.run")
    context = ContextStore().update(
        {
            "current_task": "engineering.diagnostics",
            "diagnostic_critical_count": 1,
            "diagnostic_warning_count": 0,
            "diagnostic_issue_count": 1,
        }
    )
    recommendations = RecommendationEngine().build(context)

    assert intent.intent == "engineering.diagnostics.run"
    assert capability is not None
    assert capability.read_only is True
    assert any(item.title == "Kritische Engineering-Probleme prüfen" for item in recommendations)


def test_dashboard_contains_engineering_diagnostics_area() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'id="engineeringDiagnostics"' in html
    assert 'id="runEngineeringDiagnostics"' in html
    assert 'id="diagnosticsIssueTableBody"' in html
    assert "/assistant/engineering/diagnostics/run" in js
    assert "runEngineeringDiagnostics" in js
