from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from hammer_jarvis.intent.capabilities import CapabilityRegistry
from hammer_jarvis.intent.context import ContextStore
from hammer_jarvis.intent.parser import IntentParser


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

    store.update({"active_workspace": "engineering", "active_project_name": "Retro Presse"})
    assert store.get().active_workspace == "engineering"
    assert store.get().active_project_name == "Retro Presse"

    store.reset()
    assert store.get().active_workspace is None
    assert store.get().active_project_name is None


def test_intent_api_endpoints_return_expected_payloads() -> None:
    parse_response = client.post(
        "/assistant/intent/parse",
        json={"text": "git status", "source": "api", "context": {}},
    )
    context_response = client.get("/assistant/context")
    commands_response = client.get("/assistant/commands")
    capabilities_response = client.get("/assistant/capabilities")
    reset_response = client.post("/assistant/context/reset")

    assert parse_response.status_code == 200
    assert parse_response.json()["intent"] == "development.git.status"
    assert context_response.status_code == 200
    assert commands_response.status_code == 200
    assert any(command["intent"] == "engineering.project.open" for command in commands_response.json())
    assert capabilities_response.status_code == 200
    assert any(item["id"] == "engineering.protool.preview" for item in capabilities_response.json())
    assert reset_response.status_code == 200


def test_dashboard_contains_command_palette_and_ctrl_k_hint() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")
    css = Path("app/static/dashboard.css").read_text(encoding="utf-8")

    assert 'id="commandPalette"' in html
    assert 'id="commandPaletteInput"' in html
    assert "Ctrl+K" in html
    assert "/assistant/intent/parse" in js
    assert "openCommandPalette" in js
    assert "event.ctrlKey && event.key.toLowerCase() === \"k\"" in js
    assert ".command-palette" in css

