from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from hammer_jarvis.diagnostics.models import DiagnosticIssue, DiagnosticReport
from hammer_jarvis.engineering.importer.project_importer import ProjectImporter
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphBuilder, GraphNode
from hammer_jarvis.engineering.scanner.filesystem import ProjectScanner
from hammer_jarvis.intent.context import ContextStore
from hammer_jarvis.intent.recommendations import RecommendationEngine
from hammer_jarvis.understanding.engine import EngineeringUnderstandingEngine
from hammer_jarvis.understanding.models import EngineeringObjectType
from hammer_jarvis.understanding.resolver import RelationshipResolver


client = TestClient(app)


def _diagnostic_report(affected_object_id: str = "text:demo-project:hydraulikpumpe") -> DiagnosticReport:
    issue = DiagnosticIssue(
        id="TEXT_TOO_LONG:abc123",
        rule_id="TEXT_TOO_LONG",
        severity="warning",
        category="text",
        title="Text zu lang",
        description="Der HMI-Text ist laenger als das Zielpanel.",
        affected_object_id=affected_object_id,
        affected_object_type="TextResource",
        source_file="MessageText.csv",
        source_line=2,
        evidence={"actual": 25, "max": 20},
        recommendation="Text pruefen.",
    )
    return DiagnosticReport.from_issues(
        "demo-project",
        [issue],
        executed_rules=["TEXT_TOO_LONG"],
        statistics={"read_only": True},
    )


def test_relationship_resolver_keeps_graph_edges_and_explains_relationships() -> None:
    graph = GraphBuilder().build_demo_graph()
    relationships = RelationshipResolver().resolve(graph, diagnostics=_diagnostic_report())

    assert any(item.type == "CONTAINS" for item in relationships)
    affects = [item for item in relationships if item.type == "AFFECTS"]
    assert affects
    assert affects[0].evidence
    assert "affected_object_id" in " ".join(affects[0].evidence)


def test_understanding_report_counts_objects_relationships_and_orphans() -> None:
    graph = GraphBuilder().build_demo_graph()
    graph.nodes.append(
        GraphNode(
            id="variable:orphan",
            type=EngineeringObjectType.VARIABLE,
            name="OrphanVariable",
            source_file="Variables.csv",
        )
    )

    report = EngineeringUnderstandingEngine().build(graph, diagnostics=_diagnostic_report())

    assert report.object_count == 5
    assert report.relationship_count >= 3
    assert report.object_types["Project"] == 1
    assert report.relationship_types["AFFECTS"] == 1
    assert any(item["id"] == "variable:orphan" for item in report.orphan_objects)
    assert all(relationship.evidence for relationship in report.relationships)
    asdict(report)


def test_understanding_engine_ignores_diagnostics_without_known_target() -> None:
    graph = GraphBuilder().build_demo_graph()
    report = EngineeringUnderstandingEngine().build(graph, diagnostics=_diagnostic_report("missing-node"))

    assert "AFFECTS" not in report.relationship_types


def test_understanding_engine_handles_empty_graph() -> None:
    report = EngineeringUnderstandingEngine().build(EngineeringGraph())

    assert report.object_count == 0
    assert report.relationship_count == 0
    assert report.orphan_objects == []


def test_understanding_build_is_idempotent_and_does_not_duplicate_relationships() -> None:
    graph = GraphBuilder().build_demo_graph()
    engine = EngineeringUnderstandingEngine()

    first = engine.build(graph, diagnostics=_diagnostic_report())
    second = engine.build(graph, diagnostics=_diagnostic_report())

    first_keys = {(item.source_id, item.target_id, item.type) for item in first.relationships}
    second_keys = {(item.source_id, item.target_id, item.type) for item in second.relationships}
    assert first_keys == second_keys
    assert len(second_keys) == second.relationship_count


def test_understanding_build_uses_imported_project_graph(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "RealProject"
    root.mkdir()
    (root / "MessageText.csv").write_text("ID;Text\n1;Hydraulik bereit\n", encoding="utf-8")
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(tmp_path))
    imported = ProjectImporter().import_scan(ProjectScanner().scan(root))

    report = EngineeringUnderstandingEngine().build(imported.graph)

    assert any(item.name == "MessageText.csv" for item in imported.graph.nodes)
    assert report.object_types["Project"] == 1
    assert report.object_types["ProjectFile"] == 1
    assert report.relationship_types["CONTAINS"] == 1


def test_understanding_api_build_report_relationships_and_object_resolution() -> None:
    client.post("/assistant/context/reset")
    response = client.post("/assistant/engineering/understanding/build")
    assert response.status_code == 200
    payload = response.json()
    assert payload["object_count"] >= 3
    assert payload["relationship_count"] >= 2
    assert payload["summary"]

    latest = client.get("/assistant/engineering/understanding")
    relationships = client.get("/assistant/engineering/relationships")
    object_response = client.get("/assistant/engineering/object/text:demo-project:hydraulikpumpe")
    missing = client.get("/assistant/engineering/object/missing")

    assert latest.status_code == 200
    assert relationships.status_code == 200
    assert relationships.json()["count"] == payload["relationship_count"]
    assert object_response.status_code == 200
    assert object_response.json()["type"] == "TextResource"
    assert missing.status_code == 404


def test_understanding_api_before_first_build_returns_404() -> None:
    previous_report = main_module._understanding_report
    previous_store = main_module._understanding_object_store
    main_module._understanding_report = None
    main_module._understanding_object_store = {}
    try:
        assert client.get("/assistant/engineering/understanding").status_code == 404
        assert client.get("/assistant/engineering/relationships").status_code == 404
        assert client.get("/assistant/engineering/object/text:demo-project:hydraulikpumpe").status_code == 404
    finally:
        main_module._understanding_report = previous_report
        main_module._understanding_object_store = previous_store


def test_understanding_does_not_expose_absolute_document_paths(tmp_path: Path) -> None:
    document_path = tmp_path / "manual.pdf"
    document_path.write_bytes(b"%PDF-1.4\n")
    from hammer_jarvis.documents.models import Document

    document = Document.from_path(document_path, document_type="PDF")
    report = EngineeringUnderstandingEngine().build(GraphBuilder().build_demo_graph(), documents=[document])
    payload = [relationship.metadata for relationship in report.relationships if relationship.target_id == document.id][0]

    assert str(tmp_path) not in str(payload)
    assert payload["filename"] == "manual.pdf"


def test_understanding_context_recommendation_is_created() -> None:
    context = ContextStore().update({"current_task": "engineering.understanding"})
    recommendations = RecommendationEngine().build(context)

    assert any(item.id == "engineering.understanding_model_built" for item in recommendations)


def test_dashboard_contains_engineering_understanding_card() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'id="engineeringUnderstanding"' in html
    assert 'id="buildEngineeringUnderstanding"' in html
    assert 'id="understandingObjectCount"' in html
    assert "/assistant/engineering/understanding/build" in js
    assert "renderEngineeringUnderstanding" in js
    assert "clearEngineeringUnderstanding" in js
