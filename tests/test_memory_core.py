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
    assert "Gemerkte Information" in result["answer"]
    memories = MemoryStore().search_memory("switch.hall")
    assert memories["memories"][0]["type"] == "device"
    assert memories["memories"][0]["key"] == "switch.hall"


def test_memory_command_normalizes_german_device_relation(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)

    result = AssistantOrchestrator().handle_message("Merke dir, dass switch.hall das Flur Licht ist.")
    memory = MemoryStore().search_memory("switch.hall")["memories"][0]

    assert memory["key"] == "switch.hall"
    assert memory["value"] == "Flur Licht"
    assert set(memory["tags"]) >= {"home_assistant", "smart_home", "alias", "switch"}
    assert result["answer"] == "Gemerkte Information: switch.hall ist das Flur Licht."
    assert "Flur Licht ist" not in result["answer"]


def test_memory_parser_supports_relation_variants(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)
    commands = [
        "Merke dir: switch.hall = Flur Licht",
        "Speichere switch.hall als Flur Licht.",
        "Merke dir, dass switch.hall Flur Licht bedeutet.",
    ]

    for command in commands:
        MemoryStore().delete_memory(MemoryStore().add_memory({"key": "dummy", "value": "dummy"})["id"])
        result = AssistantOrchestrator().handle_message(command)
        memory = MemoryStore().search_memory("switch.hall")["memories"][0]
        assert result["tool"] == "memory_add"
        assert memory["value"] == "Flur Licht"
        MemoryStore().delete_memory(memory["id"])


def test_memory_recall_returns_stored_memory(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)
    MemoryStore().add_memory({"type": "device", "key": "switch.hall", "value": "Flur Licht", "tags": ["home_assistant"]})

    result = AssistantOrchestrator().handle_message("Was weißt du über switch.hall?")

    assert result["tool"] == "memory_search"
    assert result["answer"] == "Ich weiß: switch.hall ist das Flur Licht."


def test_memory_recall_plural_formatting(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)
    MemoryStore().add_memory({"type": "device", "key": "switch.hall", "value": "Flur Licht"})
    MemoryStore().add_memory({"type": "device", "key": "switch.kueche", "value": "Küche Licht"})

    one = AssistantOrchestrator().handle_message("Was weißt du über switch.hall?")
    many = AssistantOrchestrator().handle_message("Was weißt du über Licht?")
    none = AssistantOrchestrator().handle_message("Was weißt du über unbekannt?")

    assert "Erinnerung(en)" not in one["answer"]
    assert "Ich weiß:" in one["answer"]
    assert "Ich habe 2 passende Erinnerungen gefunden:" in many["answer"]
    assert none["answer"] == "Ich habe keine passende Erinnerung gefunden."


def test_malformed_device_memory_is_updated_not_duplicated(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)
    existing = MemoryStore().add_memory({"type": "device", "key": "switch.hall", "value": "Flur Licht ist"})

    result = AssistantOrchestrator().handle_message("Merke dir, dass switch.hall das Flur Licht ist.")
    memories = MemoryStore().list_memory()["memories"]

    assert result["answer"] == "Erinnerung aktualisiert: switch.hall ist das Flur Licht."
    assert len(memories) == 1
    assert memories[0]["id"] == existing["id"]
    assert memories[0]["created_at"] == existing["created_at"]
    assert memories[0]["value"] == "Flur Licht"
    assert memories[0]["updated_at"] >= existing["updated_at"]


def test_memory_repair_dry_run_and_apply(monkeypatch, tmp_path: Path) -> None:
    _configure_memory(monkeypatch, tmp_path)
    MemoryStore().add_memory({"type": "device", "key": "switch.hall", "value": "Flur Licht ist"})
    MemoryStore().add_memory({"type": "fact", "key": "regel", "value": "unter 20 Prozent wichtig ist"})

    dry_run = client.post("/assistant/memory/repair", json={"dry_run": True})
    unchanged = MemoryStore().search_memory("switch.hall")["memories"][0]
    applied = client.post("/assistant/memory/repair", json={"dry_run": False})
    repaired = MemoryStore().search_memory("switch.hall")["memories"][0]
    fact = MemoryStore().search_memory("regel")["memories"][0]

    assert dry_run.json()["repairable"] == 1
    assert unchanged["value"] == "Flur Licht ist"
    assert applied.json()["changes"][0]["new_value"] == "Flur Licht"
    assert repaired["value"] == "Flur Licht"
    assert fact["value"] == "unter 20 Prozent wichtig ist"


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
