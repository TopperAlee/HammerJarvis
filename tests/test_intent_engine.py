from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from hammer_jarvis.intent.capabilities import CapabilityRegistry
from hammer_jarvis.intent.context import ContextStore
from hammer_jarvis.intent.parser import IntentParser
from hammer_jarvis.intent.recommendations import RecommendationEngine


client = TestClient(app)


def test_intent_parser_recognizes_known_commands() -> None:
    parser = IntentParser()

    cases = {
        "engineering öffnen": "engineering.workspace.open",
        "öffne projekt Retro Presse": "engineering.project.open",
        "ProTool Assistant": "engineering.protool.open",
        "analysiere protool csv": "engineering.protool.analyze",
        "Panel Vorschau": "engineering.panel.preview",
        "suche dokument Hydraulik": "knowledge.search",
        "Systemstatus": "assistant.status",
        "was kannst du": "assistant.help",
        "git status": "development.git.status",
        "pytest ausführen": "development.tests.run",
    }

    for text, expected_intent in cases.items():
        result = parser.parse_text(text, source="api")
        assert result.intent == expected_intent
        assert result.confidence > 0
        assert result.risk == "GREEN"


def test_intent_parser_unknown_command_returns_unknown() -> None:
    result = IntentParser().parse_text("mach irgendwas unbekanntes", source="chat")

    assert result.intent == "unknown"
    assert result.confidence == 0.0
    assert result.source == "chat"
    assert "nicht eindeutig" in result.message


def test_capability_registry_contains_protool_preview() -> None:
    capability = CapabilityRegistry().get("engineering.protool.preview")

    assert capability is not None
    assert capability.name == "ProTool Panel Preview"
    assert capability.read_only is True
    assert capability.risk_level == "GREEN"


def test_context_store_update_and_reset() -> None:
    store = ContextStore()

    initial_updated_at = store.get().updated_at

    store.update(
        {
            "active_workspace": "engineering",
            "active_project_name": "Retro Presse",
            "active_project_path": "C:/Projects/RetroPresse",
            "active_file_type": "MESSAGE_TEXT",
            "last_selected_node": "node-1",
        }
    )
    assert store.get().active_workspace == "engineering"
    assert store.get().active_project_name == "Retro Presse"
    assert store.get().active_project_path == "C:/Projects/RetroPresse"
    assert store.get().active_file_type == "MESSAGE_TEXT"
    assert store.get().last_selected_node == "node-1"
    assert store.get().updated_at is not None
    assert store.get().updated_at != initial_updated_at

    store.reset()
    assert store.get().active_workspace is None
    assert store.get().active_project_name is None
    assert store.get().active_project_path is None
    assert store.get().updated_at is not None


def test_recommendation_engine_returns_project_open_without_active_project() -> None:
    recommendations = RecommendationEngine().build(ContextStore().get())

    assert any(item.id == "engineering.open_project" for item in recommendations)
    assert any(item.title == "Projekt öffnen" for item in recommendations)


def test_recommendation_engine_returns_contextual_engineering_recommendations() -> None:
    context = ContextStore().update(
        {
            "active_workspace": "engineering",
            "active_project_id": "project-1",
            "active_project_name": "Retro Presse",
            "active_file": "MessageText.csv",
            "active_file_type": "MESSAGE_TEXT",
            "active_panel": "OP7",
            "current_task": "protool_analysis_has_issues",
        }
    )

    recommendations = RecommendationEngine(
        knowledge_empty=True,
        voice_ready=False,
    ).build(context)

    ids = {item.id for item in recommendations}
    assert "engineering.analyze_project_files" in ids
    assert "engineering.protool_analyze_active_csv" in ids
    assert "engineering.protool_check_panel_preview" in ids
    assert "knowledge.index_documents" in ids
    assert "voice.check_status" in ids


def test_intent_api_endpoints_return_expected_payloads() -> None:
    parse_response = client.post(
        "/assistant/intent/parse",
        json={"text": "git status", "source": "api", "context": {}},
    )
    context_response = client.get("/assistant/context")
    commands_response = client.get("/assistant/commands")
    capabilities_response = client.get("/assistant/capabilities")
    context_update_response = client.post(
        "/assistant/context/update",
        json={"active_workspace": "engineering", "active_project_name": "Retro Presse"},
    )
    recommendations_response = client.get("/assistant/recommendations")
    reset_response = client.post("/assistant/context/reset")

    assert parse_response.status_code == 200
    assert parse_response.json()["intent"] == "development.git.status"
    assert context_response.status_code == 200
    assert commands_response.status_code == 200
    assert any(command["intent"] == "engineering.project.open" for command in commands_response.json())
    assert capabilities_response.status_code == 200
    assert any(item["id"] == "engineering.protool.preview" for item in capabilities_response.json())
    assert context_update_response.status_code == 200
    assert context_update_response.json()["active_workspace"] == "engineering"
    assert context_update_response.json()["updated_at"]
    assert recommendations_response.status_code == 200
    assert any(item["id"] for item in recommendations_response.json())
    assert reset_response.status_code == 200


def test_dashboard_contains_command_palette_and_ctrl_k_hint() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")
    css = Path("app/static/dashboard.css").read_text(encoding="utf-8")

    assert 'id="commandPalette"' in html
    assert 'id="commandPaletteInput"' in html
    assert 'id="activeContextList"' in html
    assert 'id="recommendationsList"' in html
    assert "Ctrl+K" in html
    assert "/assistant/intent/parse" in js
    assert "/assistant/context" in js
    assert "/assistant/recommendations" in js
    assert "refreshCommandCenter" in js
    assert "openCommandPalette" in js
    assert "event.ctrlKey && event.key.toLowerCase() === \"k\"" in js
    assert ".command-palette" in css
