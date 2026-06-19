from pathlib import Path

from fastapi.testclient import TestClient

from app.assistant.knowledge.chunker import chunk_text
from app.assistant.knowledge.embedding_client import OllamaEmbeddingClient
from app.assistant.knowledge.knowledge_store import KnowledgeStore
from app.assistant.orchestrator import AssistantOrchestrator
from app.main import app


client = TestClient(app)


def test_chunking_uses_overlap() -> None:
    chunks = chunk_text("abcdefghijklmnopqrstuvwxyz", chunk_size=10, overlap=3)

    assert chunks[0]["text"] == "abcdefghij"
    assert chunks[1]["text"].startswith("hij")


def test_text_file_indexing_and_search(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    document = tmp_path / "docs" / "hauskauf.txt"
    document.parent.mkdir()
    document.write_text("Der Kaufvertrag nennt den Notartermin und Energieausweis.", encoding="utf-8")

    indexed = KnowledgeStore().index_text_file(document)
    result = KnowledgeStore().search_knowledge("Energieausweis")

    assert indexed["indexed"] is True
    assert result["count"] == 1
    assert result["results"][0]["document_name"] == "hauskauf.txt"


def test_files_outside_allowed_dirs_are_rejected(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("geheim", encoding="utf-8")

    result = KnowledgeStore().index_text_file(outside)

    assert result["blocked"] is True
    assert result["reason"] == "outside_allowed_dirs"


def test_env_and_secrets_are_not_indexed(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    env_file = tmp_path / "docs" / ".env"
    secret_file = tmp_path / "docs" / "app" / "secrets" / "token.txt"
    secret_file.parent.mkdir(parents=True)
    env_file.write_text("TOKEN=secret", encoding="utf-8")
    secret_file.write_text("secret", encoding="utf-8")

    env_result = KnowledgeStore().index_text_file(env_file)
    secret_result = KnowledgeStore().index_text_file(secret_file)

    assert env_result["blocked"] is True
    assert secret_result["blocked"] is True


def test_missing_embedding_model_returns_clear_message(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("app.assistant.knowledge.embedding_client.requests.post", fail)

    result = OllamaEmbeddingClient().embed("test")

    assert result["error"] is True
    assert "ollama pull nomic-embed-text" in result["message"]


def test_knowledge_endpoints(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    document = tmp_path / "docs" / "projekt.md"
    document.parent.mkdir()
    document.write_text("Hammer Jarvis nutzt lokale Werkzeuge.", encoding="utf-8")

    indexed = client.post("/assistant/knowledge/index", json={"path": str(document)})
    searched = client.get("/assistant/knowledge/search?q=lokale%20Werkzeuge")
    documents = client.get("/assistant/knowledge/documents")

    assert indexed.status_code == 200
    assert searched.status_code == 200
    assert searched.json()["count"] == 1
    assert documents.json()["count"] == 1


def test_knowledge_search_command_bypasses_llm(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    document = tmp_path / "docs" / "hauskauf.txt"
    document.parent.mkdir()
    document.write_text("Im Hauskauf geht es um den Energieausweis.", encoding="utf-8")
    KnowledgeStore().index_text_file(document)

    result = AssistantOrchestrator().handle_message("Suche im Wissensspeicher nach Energieausweis")

    assert result["tool"] == "knowledge_search"
    assert "hauskauf.txt" in result["answer"]


def _configure_knowledge(monkeypatch, tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    monkeypatch.setenv("KNOWLEDGE_ENABLED", "true")
    monkeypatch.setenv("KNOWLEDGE_STORE_FILE", str(tmp_path / "knowledge_index.json"))
    monkeypatch.setenv("KNOWLEDGE_ALLOWED_DIRS", str(docs))
    monkeypatch.setenv("KNOWLEDGE_CHUNK_SIZE", "40")
    monkeypatch.setenv("KNOWLEDGE_CHUNK_OVERLAP", "5")
    monkeypatch.setenv("KNOWLEDGE_MAX_RESULTS", "8")
    monkeypatch.setenv("LLM_ENABLED", "false")
