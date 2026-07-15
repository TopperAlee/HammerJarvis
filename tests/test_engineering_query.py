from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module
from app.assistant.orchestrator import AssistantOrchestrator, _parse_home_assistant_action_intent
from app.main import app
from hammer_jarvis.diagnostics.models import DiagnosticIssue, DiagnosticReport
from hammer_jarvis.documents.models import Document, DocumentContent
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphBuilder, GraphEdge, GraphNode
from hammer_jarvis.query.engine import EngineeringCopilotAnswerBuilder, EngineeringQueryEngine
from hammer_jarvis.query.explanations import relationship_id
from hammer_jarvis.query.models import EngineeringQueryRequest, EngineeringQueryType
from hammer_jarvis.query.parser import EngineeringQueryParser
from hammer_jarvis.research.answer_engine import MockResearchLLM
from hammer_jarvis.understanding.engine import EngineeringUnderstandingEngine


client = TestClient(app)


def _diagnostic_report() -> DiagnosticReport:
    issue = DiagnosticIssue(
        id="TEXT_TOO_LONG:query",
        rule_id="TEXT_TOO_LONG",
        severity="warning",
        category="text",
        title="Text zu lang",
        description="Der HMI-Text ist laenger als das Zielpanel.",
        affected_object_id="text:demo-project:hydraulikpumpe",
        affected_object_type="TextResource",
        source_file="C:/secret/MessageText.csv",
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


def _engine(tmp_path: Path) -> EngineeringQueryEngine:
    graph = GraphBuilder().build_demo_graph()
    document_path = tmp_path / "manual.pdf"
    document_path.write_bytes(b"%PDF-1.4\n")
    document = Document.from_path(document_path, "PDF")
    diagnostics = _diagnostic_report()
    report = EngineeringUnderstandingEngine().build(graph, diagnostics=diagnostics, documents=[document])
    objects = {node.id: asdict(node) for node in graph.nodes}
    objects[f"diagnostic:{diagnostics.issues[0].id}"] = {
        "id": f"diagnostic:{diagnostics.issues[0].id}",
        "type": "Diagnostic",
        "name": diagnostics.issues[0].title,
        "source_file": diagnostics.issues[0].source_file,
        "source_line": diagnostics.issues[0].source_line,
        "metadata": {"rule_id": diagnostics.issues[0].rule_id, "severity": diagnostics.issues[0].severity},
    }
    objects[document.id] = {
        "id": document.id,
        "type": "Manual",
        "name": document.filename,
        "source_file": document.path,
        "source_line": None,
        "metadata": {"mime_type": document.mime_type},
    }
    return EngineeringQueryEngine(
        graph=graph,
        understanding=report,
        objects=objects,
        diagnostics=diagnostics,
        documents=[document],
    )


def test_query_parser_recognizes_required_query_types() -> None:
    parser = EngineeringQueryParser()

    cases = {
        "welche beziehungen hat Hydraulikpumpe": EngineeringQueryType.RELATIONSHIPS,
        "wo wird Hydraulikpumpe verwendet": EngineeringQueryType.USAGE,
        "welche diagnosen betreffen Hydraulikpumpe": EngineeringQueryType.DIAGNOSTICS,
        "welche dokumente gehoeren zu Beispielprojekt": EngineeringQueryType.DOCUMENTS,
        "zeige verwaiste objekte": EngineeringQueryType.ORPHANS,
        "zeige alle alarme": EngineeringQueryType.LIST_OBJECT_TYPE,
        "zeige alle variablen": EngineeringQueryType.LIST_OBJECT_TYPE,
        "zeige alle texte": EngineeringQueryType.LIST_OBJECT_TYPE,
        "zeige alle dokumente": EngineeringQueryType.LIST_OBJECT_TYPE,
        "irgendwas anderes": EngineeringQueryType.UNKNOWN,
    }

    for query, expected_type in cases.items():
        assert parser.parse(query).query_type == expected_type


def test_query_engine_search_relationships_diagnostics_documents_and_limit(tmp_path: Path) -> None:
    engine = _engine(tmp_path)

    search = engine.execute(EngineeringQueryRequest(query="finde objekt Hydraulikpumpe"))
    relationships = engine.execute(EngineeringQueryRequest(query="welche beziehungen hat Hydraulikpumpe"))
    diagnostics = engine.execute(EngineeringQueryRequest(query="welche diagnosen betreffen Hydraulikpumpe"))
    documents = engine.execute(EngineeringQueryRequest(query="welche dokumente gehoeren zu Beispielprojekt"))
    limited = engine.execute(EngineeringQueryRequest(query="zeige alle texte", limit=1))

    assert search.matched_objects[0].object_id == "text:demo-project:hydraulikpumpe"
    assert any(item["direction"] == "incoming" for item in relationships.relationships)
    assert diagnostics.diagnostics[0]["source_file"] == "MessageText.csv"
    assert documents.documents[0]["filename"] == "manual.pdf"
    assert len(limited.matched_objects) == 1


def test_query_engine_orphans_empty_graph_and_deterministic_sorting(tmp_path: Path) -> None:
    graph = GraphBuilder().build_demo_graph()
    graph.nodes.append(GraphNode(id="variable:z", type="Variable", name="Zeta", source_file="Variables.csv"))
    graph.nodes.append(GraphNode(id="variable:a", type="Variable", name="Alpha", source_file="Variables.csv"))
    report = EngineeringUnderstandingEngine().build(graph)
    objects = {node.id: asdict(node) for node in graph.nodes}
    engine = EngineeringQueryEngine(graph=graph, understanding=report, objects=objects)

    orphans = engine.execute(EngineeringQueryRequest(query="zeige verwaiste objekte"))
    variables = engine.execute(EngineeringQueryRequest(query="zeige alle variablen"))
    empty_report = EngineeringUnderstandingEngine().build(EngineeringGraph())
    empty = EngineeringQueryEngine(graph=EngineeringGraph(), understanding=empty_report, objects={}).execute(
        EngineeringQueryRequest(query="finde objekt Hydraulik")
    )

    assert {item.object_id for item in orphans.matched_objects} == {"variable:a", "variable:z"}
    assert [item.name for item in variables.matched_objects] == ["Alpha", "Zeta"]
    assert empty.matched_objects == []
    assert empty.recommendations == ["Projekt oder Suchbegriff pruefen"]


def test_query_engine_uses_real_imported_graph_shape() -> None:
    graph = EngineeringGraph(
        nodes=[
            GraphNode(id="project:real", type="Project", name="Real", source_file=None),
            GraphNode(id="file:real:MessageText.csv", type="ProjectFile", name="MessageText.csv", source_file="MessageText.csv"),
            GraphNode(id="text:real:hydraulik", type="TextResource", name="Hydraulik bereit", source_file="MessageText.csv"),
        ],
        edges=[
            GraphEdge(source_id="project:real", target_id="file:real:MessageText.csv", type="CONTAINS"),
            GraphEdge(source_id="file:real:MessageText.csv", target_id="text:real:hydraulik", type="DEFINES"),
        ],
    )
    report = EngineeringUnderstandingEngine().build(graph)
    engine = EngineeringQueryEngine(graph=graph, understanding=report, objects={node.id: asdict(node) for node in graph.nodes})

    result = engine.execute(EngineeringQueryRequest(query="wo wird Hydraulik verwendet"))

    assert result.query_type == EngineeringQueryType.USAGE
    assert result.relationships[0]["type"] == "DEFINES"


def test_explainability_uses_evidence_and_hides_absolute_paths(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = engine.execute(EngineeringQueryRequest(query="welche beziehungen hat Hydraulikpumpe"))
    explanation = result.explanations[0]

    assert explanation["evidence"]["existing_edge"] is True
    assert "source_type" in explanation["evidence"]
    assert str(tmp_path) not in str(result.model_dump())
    assert engine.explain_relationship(result.relationships[0]["id"])["reason"]


def test_explainability_unknown_relationship_returns_error(tmp_path: Path) -> None:
    engine = _engine(tmp_path)

    try:
        engine.explain_relationship("relationship:missing")
    except Exception as exc:
        assert getattr(exc, "status_code") == 404
    else:
        raise AssertionError("Expected unknown relationship to fail")


def test_copilot_mock_llm_and_deterministic_fallback(tmp_path: Path) -> None:
    result = _engine(tmp_path).execute(EngineeringQueryRequest(query="finde objekt Hydraulikpumpe"))
    fallback = EngineeringCopilotAnswerBuilder().build(result)
    llm_answer = EngineeringCopilotAnswerBuilder(MockResearchLLM()).build(result)

    assert "Query-Typ" in fallback
    assert "Deterministische Research-Antwort" in llm_answer
    assert result.explanations or result.matched_objects


def test_engineering_query_api_endpoints_and_context(tmp_path: Path) -> None:
    client.post("/assistant/context/reset")
    main_module._understanding_report = None
    main_module._understanding_object_store = {}
    assert client.post("/assistant/engineering/query", json={"query": "finde objekt Hydraulik"}).status_code == 409

    build = client.post("/assistant/engineering/understanding/build")
    assert build.status_code == 200
    query = client.post("/assistant/engineering/query", json={"query": "wo wird Hydraulikpumpe verwendet"})
    latest = client.get("/assistant/engineering/query/latest")
    types = client.get("/assistant/engineering/query/types")
    obj = client.get("/assistant/engineering/query/object/text:demo-project:hydraulikpumpe")
    relationship_hash = query.json()["relationships"][0]["id"].removeprefix("relationship:")
    explanation = client.get(f"/assistant/engineering/query/relationship/{relationship_hash}/explain")
    context = client.get("/assistant/context")

    assert query.status_code == 200
    assert latest.status_code == 200
    assert types.status_code == 200
    assert obj.status_code == 200
    assert explanation.status_code == 200
    assert context.json()["last_intent"] == "engineering.query"
    assert context.json()["current_task"] == "engineering.query"
    assert client.post("/assistant/engineering/query", json={"query": "   "}).status_code == 400
    assert client.get("/assistant/engineering/query/object/missing").status_code == 404


def test_engineering_query_capability_intents_recommendations_and_dashboard() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert any(item["id"] == "engineering.query" for item in client.get("/assistant/capabilities").json())
    assert client.post("/assistant/intent/parse", json={"text": "wo wird Hydraulik verwendet"}).json()["intent"] == "engineering.query"
    assert client.post("/assistant/intent/parse", json={"text": "zeige Beziehungen"}).json()["intent"] == "engineering.object.relationships"
    assert client.post("/assistant/intent/parse", json={"text": "welche Diagnosen betreffen diese Datei"}).json()["intent"] == "engineering.object.diagnostics"
    assert client.post("/assistant/intent/parse", json={"text": "zeige Dokumente zum Projekt"}).json()["intent"] == "engineering.object.documents"
    assert client.post("/assistant/intent/parse", json={"text": "zeige verwaiste Objekte"}).json()["intent"] == "engineering.object.orphans"
    assert 'id="engineeringCopilotCard"' in html
    assert 'id="engineeringCopilotInput"' in html
    assert "runEngineeringCopilotQuery" in js
    assert "/assistant/engineering/query" in js
    assert ".innerHTML" not in "\n".join(line for line in js.splitlines() if "engineeringCopilot" in line)
    assert "Wo wird Hydraulik verwendet?" in str(client.get("/assistant/commands").json())


def test_assistant_chat_routes_engineering_usage_before_ha_and_llm(monkeypatch) -> None:
    main_module._understanding_report = None
    main_module._understanding_object_store = {}

    def fail_ha(*args, **kwargs):
        raise AssertionError("Engineering query must not reach Home Assistant handlers")

    def fail_llm(*args, **kwargs):
        raise AssertionError("Engineering query must not reach LLM fallback")

    monkeypatch.setattr(AssistantOrchestrator, "_handle_home_assistant_control_command", fail_ha)
    monkeypatch.setattr(AssistantOrchestrator, "_handle_home_assistant_action_command", fail_ha)
    monkeypatch.setattr(AssistantOrchestrator, "_handle_llm", fail_llm)

    response = client.post("/assistant/chat", json={"message": "Wo wird Hydraulikpumpe verwendet?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool"] == "engineering.query"
    assert payload["mode"] == "engineering_query"
    assert payload["query_type"] == "USAGE"
    assert payload["result"]["query_type"] == "USAGE"
    assert payload["result"]["status"] == "OK"


def test_assistant_chat_missing_engineering_object_is_deterministic_and_not_ha_or_llm(monkeypatch) -> None:
    main_module._understanding_report = None
    main_module._understanding_object_store = {}

    def fail_ha(*args, **kwargs):
        raise AssertionError("Missing engineering object must not reach Home Assistant handlers")

    def fail_llm(*args, **kwargs):
        raise AssertionError("Missing engineering object must not reach LLM fallback")

    monkeypatch.setattr(AssistantOrchestrator, "_handle_home_assistant_control_command", fail_ha)
    monkeypatch.setattr(AssistantOrchestrator, "_handle_home_assistant_action_command", fail_ha)
    monkeypatch.setattr(AssistantOrchestrator, "_handle_llm", fail_llm)

    response = client.post(
        "/assistant/chat",
        json={"message": "Welche Beziehungen hat ein nicht existierendes Objekt?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool"] == "engineering.query"
    assert payload["query_type"] == "RELATIONSHIPS"
    assert payload["status"] == "OBJECT_NOT_FOUND"
    assert payload["error_code"] == "OBJECT_NOT_FOUND"
    assert payload["result"]["matched_objects"] == []
    assert payload["result"]["statistics"]["reason"] == "OBJECT_NOT_FOUND"
    assert payload["answer"]


def test_home_assistant_unsafe_words_require_explicit_control_intent() -> None:
    assert _parse_home_assistant_action_intent("wo wird hydraulikpumpe verwendet") is None

    blocked = _parse_home_assistant_action_intent("schalte die hydraulikpumpe ein")

    assert blocked == {"target": "schalte die hydraulikpumpe ein", "action": "blocked"}


def test_manual_acceptance_engineering_chat_routes() -> None:
    usage = client.post("/assistant/chat", json={"message": "Wo wird Hydraulikpumpe verwendet?"}).json()
    missing = client.post(
        "/assistant/chat",
        json={"message": "Welche Beziehungen hat ein nicht existierendes Objekt?"},
    ).json()

    print(
        "ACCEPTANCE_USAGE",
        {
            "tool": usage.get("tool"),
            "mode": usage.get("mode"),
            "query_type": usage.get("query_type"),
            "status": usage.get("status"),
        },
    )
    print(
        "ACCEPTANCE_MISSING",
        {
            "tool": missing.get("tool"),
            "mode": missing.get("mode"),
            "query_type": missing.get("query_type"),
            "status": missing.get("status"),
            "error_code": missing.get("error_code"),
        },
    )
    assert usage["tool"] == "engineering.query"
    assert usage["query_type"] == "USAGE"
    assert missing["tool"] == "engineering.query"
    assert missing["query_type"] == "RELATIONSHIPS"
    assert missing["status"] == "OBJECT_NOT_FOUND"
