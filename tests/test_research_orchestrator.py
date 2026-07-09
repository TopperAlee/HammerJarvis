from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from hammer_jarvis.research.context_builder import ContextBuilder
from hammer_jarvis.research.models import ResearchRequest, ResearchSource
from hammer_jarvis.research.orchestrator import ResearchOrchestrator
from hammer_jarvis.research.sources import available_research_sources


client = TestClient(app)


def test_research_models_are_json_compatible() -> None:
    request = ResearchRequest(query="Hydraulikpumpe", active_context={"active_workspace": "engineering"})
    source = ResearchSource(
        id="graph:1",
        type="GRAPH",
        title="Hydraulikpumpe pruefen",
        summary="TextResource Treffer",
        relevance=0.9,
        metadata={"node_type": "TextResource"},
    )

    payload = asdict(source)

    assert request.include_web is False
    assert payload["type"] == "GRAPH"
    assert payload["metadata"]["node_type"] == "TextResource"


def test_research_orchestrator_combines_graph_knowledge_and_capabilities(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KNOWLEDGE_ENABLED", "true")
    monkeypatch.setenv("KNOWLEDGE_STORE_FILE", str(tmp_path / "knowledge.json"))
    monkeypatch.setenv("KNOWLEDGE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("KNOWLEDGE_ALLOWED_DIRS", str(tmp_path))
    document = tmp_path / "hydraulik.txt"
    document.write_text("Hydraulikpumpe Dokumentation fuer OP7.", encoding="utf-8")
    indexed = client.post("/assistant/knowledge/index", json={"path": str(document)})
    assert indexed.status_code == 200

    context = ResearchOrchestrator().build_context(ResearchRequest(query="Hydraulikpumpe"))

    source_types = {source.type for source in context.sources}
    assert {"GRAPH", "KNOWLEDGE", "CAPABILITY"}.issubset(source_types)
    assert context.request.include_web is False
    assert context.statistics["source_count"] == len(context.sources)
    assert context.statistics["web_enabled"] is False
    assert "Benutzerfrage" in context.prompt
    assert "Hydraulikpumpe" in context.prompt


def test_context_builder_creates_structured_prompt_without_web_section() -> None:
    request = ResearchRequest(
        query="Panel Vorschau",
        active_context={"active_project_name": "Retro Presse"},
        active_project="Retro Presse",
        active_file="MessageText.csv",
        active_panel="OP7",
    )
    source = ResearchSource(
        id="capability:engineering.protool.preview",
        type="CAPABILITY",
        title="ProTool Panel Preview",
        summary="Lokale read-only Vorschau.",
        relevance=0.7,
        metadata={"risk_level": "GREEN"},
    )

    prompt = ContextBuilder().build_prompt(request, [source])

    assert "System" in prompt
    assert "Aktueller Kontext" in prompt
    assert "Capabilities" in prompt
    assert "ProTool Panel Preview" in prompt
    assert "Websuche" not in prompt


def test_research_api_endpoints_return_context_and_sources() -> None:
    context_response = client.post("/assistant/research/context", json={"query": "Hydraulikpumpe"})
    sources_response = client.get("/assistant/research/sources")

    assert context_response.status_code == 200
    data = context_response.json()
    assert data["request"]["query"] == "Hydraulikpumpe"
    assert data["request"]["include_web"] is False
    assert isinstance(data["sources"], list)
    assert "prompt" in data
    assert sources_response.status_code == 200
    sources = sources_response.json()
    assert any(source["id"] == "GRAPH" and source["type"] == "GRAPH" and source["enabled"] is True for source in sources)
    assert any(source["id"] == "WEB" and source["type"] == "WEB" and source["enabled"] is False for source in sources)


def test_research_sources_are_documented_as_local_only() -> None:
    sources = available_research_sources()

    assert any(source["type"] == "DOCUMENT" for source in sources)
    assert next(source for source in sources if source["type"] == "WEB")["enabled"] is False


def test_dashboard_contains_research_context_card() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'id="researchContextQuery"' in html
    assert 'id="researchSourceCount"' in html
    assert 'id="researchContextSize"' in html
    assert "/assistant/research/context" in js
    assert "refreshResearchContext" in js
