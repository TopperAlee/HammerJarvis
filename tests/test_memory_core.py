from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.assistant.memory.memory_store import MemoryStore
from app.assistant.orchestrator import AssistantOrchestrator
from app.main import app


client = TestClient(app)


def test_add_search_delete_memory(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)
    store = MemoryStore()

    added = store.add_memory({"type": "device", "key": "switch.hall", "value": "Flur Licht", "tags": ["home_assistant"]})
    found = store.search_memory("Flur")
    deleted = store.delete_memory(added["id"])

    assert added["id"]
    assert found["count"] == 1
    assert deleted["deleted"] is True
    assert store.search_memory("Flur")["count"] == 0


def test_memory_command_stores_device_memory(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)

    result = AssistantOrchestrator().handle_message("Merke dir, dass switch.hall das Flurlicht ist.")

    assert result["tool"] == "memory_add"
    assert "gespeichert" in result["answer"]
    memories = MemoryStore().search_memory("switch.hall")
    assert memories["memories"][0]["type"] == "device"
    assert memories["memories"][0]["key"] == "switch.hall"


def test_memory_recall_returns_stored_memory(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)
    MemoryStore().add_memory({"type": "device", "key": "switch.hall", "value": "Flur Licht", "tags": ["home_assistant"]})

    result = AssistantOrchestrator().handle_message("Was weißt du über switch.hall?")

    assert result["tool"] == "memory_search"
    assert "switch.hall" in result["answer"]
    assert "Flur Licht" in result["answer"]


def test_api_keys_are_not_stored(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)

    result = AssistantOrchestrator().handle_message("Merke dir, dass mein API Key sk-1234567890abcdef ist.")

    assert result["blocked"] is True
    assert "speichere ich nicht" in result["answer"]
    assert MemoryStore().list_memory()["count"] == 0


def test_bearer_token_pattern_is_blocked(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)

    result = AssistantOrchestrator().handle_message("Speichere, dass bearer abc.def.ghi mein Token ist.")

    assert result["blocked"] is True
    assert MemoryStore().list_memory()["count"] == 0


def test_ambiguous_correction_asks_for_confirmation(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)

    result = AssistantOrchestrator().handle_message("Nein, switch.hall ist das Flurlicht.")

    assert result["tool"] == "memory_suggestion"
    assert "Soll ich mir merken" in result["answer"]
    assert result["pending_actions"][0]["risk"] == "YELLOW"


def test_memory_context_is_included_in_llm_prompt(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)
    MemoryStore().add_memory({"type": "project", "key": "Projekt X", "value": "nutzt lokale Tools", "tags": ["projekt"]})
    captured: dict[str, Any] = {}

    class FakeLLM:
        def is_available(self) -> bool:
            return True

        def create_response_with_tools(self, messages, tools):
            captured["messages"] = messages
            return {"text": "Antwort", "tool_calls": []}

    result = AssistantOrchestrator(llm_client=FakeLLM()).handle_message("Erzähl mir etwas zu Projekt X")

    assert result["tool"] == "general_answer"
    assert "Lokaler Memory-Kontext" in captured["messages"][1]["content"]
    assert "Projekt X" in captured["messages"][1]["content"]


def test_memory_does_not_auto_allow_smart_home_control(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)
    MemoryStore().add_memory({"type": "device", "key": "switch.secret", "value": "Geheimes Licht"})

    result = AssistantOrchestrator().handle_message("Geheimes Licht einschalten")

    assert result.get("tool") != "home_assistant_execute_control_action"
    assert not result.get("pending_actions")


def test_memory_endpoints(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)

    created = client.post("/assistant/memory", json={"type": "preference", "key": "LOTTO24", "value": "unwichtig"})
    searched = client.get("/assistant/memory/search?q=LOTTO24")
    deleted = client.delete(f"/assistant/memory/{created.json()['id']}")

    assert created.status_code == 200
    assert searched.status_code == 200
    assert searched.json()["count"] == 1
    assert deleted.json()["deleted"] is True


def _configure_memory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORY_ENABLED", "true")
    monkeypatch.setenv("MEMORY_FILE", str(tmp_path / "memory.json"))
    monkeypatch.setenv("MEMORY_MAX_ITEMS", "1000")
    monkeypatch.setenv("LLM_ENABLED", "false")
