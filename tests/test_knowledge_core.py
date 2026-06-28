import json
import multiprocessing
import os
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from app.assistant.knowledge.chunker import chunk_text
from app.assistant.knowledge.embedding_client import OllamaEmbeddingClient
from app.assistant.knowledge import knowledge_store as knowledge_store_module
from app.assistant.knowledge.knowledge_store import KnowledgeStore
from app.assistant.orchestrator import AssistantOrchestrator
from app.main import app


client = TestClient(app)


def _concurrent_upload_worker(index_path: str, upload_dir: str, filename: str, content: bytes, start_event, result_queue) -> None:
    """Spawn-safe worker used to verify the JSON index is protected across processes."""

    os.environ["KNOWLEDGE_STORE_FILE"] = index_path
    os.environ["KNOWLEDGE_UPLOAD_DIR"] = upload_dir
    start_event.wait(timeout=10)
    result_queue.put(KnowledgeStore().store_upload(filename, content)["stored"])


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


def test_default_storage_uses_localappdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KNOWLEDGE_STORE_FILE", raising=False)
    monkeypatch.delenv("KNOWLEDGE_UPLOAD_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))

    store = KnowledgeStore()

    assert store.path == tmp_path / "localappdata" / "HammerJarvis" / "knowledge" / "knowledge_index.json"
    assert store.upload_dir == tmp_path / "localappdata" / "HammerJarvis" / "knowledge" / "uploads"


def test_upload_uses_sha256_deduplication_without_second_file(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("KNOWLEDGE_UPLOAD_DIR", str(upload_dir))

    store = KnowledgeStore()
    first = store.store_upload("notizen.txt", b"Lokales Wissen", "text/plain")
    second = store.store_upload("kopie.txt", b"Lokales Wissen", "text/plain")

    assert first["stored"] is True
    assert second["duplicate"] is True
    assert second["document"]["document_id"] == first["document"]["document_id"]
    assert len(list(upload_dir.iterdir())) == 1


def test_upload_rejects_traversal_and_invalid_pdf_signature(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()

    traversal = store.store_upload("../notizen.txt", b"nicht speichern")
    invalid_pdf = store.store_upload("bericht.pdf", b"kein pdf")

    assert traversal["reason"] == "invalid_filename"
    assert invalid_pdf["reason"] == "invalid_pdf_header"


def test_upload_document_contains_required_metadata(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    document = KnowledgeStore().store_upload("wissen.md", b"# Lokales Wissen", "text/markdown")["document"]

    assert {
        "document_id", "original_name", "stored_name", "path", "extension", "mime_type",
        "size_bytes", "sha256", "uploaded_at", "indexed_at", "modified_at", "chunk_count",
        "extraction_status", "extraction_message", "source_type",
    }.issubset(document)
    assert document["source_type"] == "upload"


def test_concurrent_process_uploads_do_not_lose_index_entries(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    index_path = str(tmp_path / "knowledge_index.json")
    upload_dir = str(tmp_path / "uploads")
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=_concurrent_upload_worker,
            args=(index_path, upload_dir, f"wissen-{number}.txt", f"Inhalt {number}".encode(), start_event, results),
        )
        for number in range(4)
    ]
    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(timeout=15)

    assert all(process.exitcode == 0 for process in processes)
    assert [results.get(timeout=2) for _ in processes] == [True] * len(processes)
    assert KnowledgeStore().list_documents()["count"] == len(processes)


def test_upload_removes_file_when_index_write_fails(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("KNOWLEDGE_UPLOAD_DIR", str(upload_dir))
    store = KnowledgeStore()

    def fail_save(data, *, create_backup=True):
        raise OSError("disk full")

    monkeypatch.setattr(store, "_save_unlocked", fail_save)
    result = store.store_upload("abbruch.txt", "temporärer Inhalt".encode("utf-8"))

    assert result["stored"] is False
    assert result["reason"] == "index_write_failed"
    assert not list(upload_dir.glob("*"))


def test_delete_rolls_back_renamed_upload_when_index_write_fails(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()
    document = store.store_upload("behalten.txt", b"wichtig")["document"]
    source = Path(document["path"])

    def fail_save(data, *, create_backup=True):
        raise OSError("disk full")

    monkeypatch.setattr(store, "_save_unlocked", fail_save)
    result = store.delete_document(document["document_id"])

    assert result["deleted"] is False
    assert result["reason"] == "index_write_failed"
    assert source.exists()
    assert store.get_document(document["document_id"])["found"] is True


def test_reindex_does_not_resurrect_document_deleted_during_extraction(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()
    document = store.store_upload("rennen.txt", b"Inhalt")["document"]
    extraction_started = threading.Event()
    continue_extraction = threading.Event()
    result_box: dict[str, object] = {}

    def delayed_extraction(path: Path) -> dict[str, object]:
        extraction_started.set()
        assert continue_extraction.wait(timeout=5)
        return {"skipped": False, "error": False, "text": "indexierter Inhalt"}

    monkeypatch.setattr(knowledge_store_module, "extract_text", delayed_extraction)
    worker = threading.Thread(target=lambda: result_box.update(store.reindex_document(document["document_id"])))
    worker.start()
    assert extraction_started.wait(timeout=5)
    deleted = store.delete_document(document["document_id"])
    continue_extraction.set()
    worker.join(timeout=5)

    assert deleted["deleted"] is True
    assert result_box["reason"] == "document_not_found"
    assert store.get_document(document["document_id"])["found"] is False


def test_corrupt_index_without_valid_backup_returns_recovery_error(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{corrupt", encoding="utf-8")

    listed = store.list_documents()
    uploaded = store.store_upload("nicht_speichern.txt", b"Inhalt")

    assert listed["reason"] == "index_recovery_failed"
    assert uploaded["reason"] == "index_recovery_failed"
    assert store.path.read_text(encoding="utf-8") == "{corrupt"


def test_corrupt_index_with_invalid_backup_returns_recovery_error(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{corrupt", encoding="utf-8")
    store.backup_path.write_text("[also corrupt", encoding="utf-8")

    result = store.status()

    assert result["reason"] == "index_recovery_failed"
    assert store.path.read_text(encoding="utf-8") == "{corrupt"


def test_upload_write_failure_returns_structured_error(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()

    def fail_write(target: Path, content: bytes) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(store, "_write_upload_file", fail_write)

    result = store.store_upload("readonly.txt", b"Inhalt")

    assert result == {"stored": False, "error": True, "reason": "upload_write_failed"}


def test_indexing_replaces_legacy_record_with_same_path(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    source = tmp_path / "docs" / "alt.txt"
    source.parent.mkdir()
    source.write_text("Aktueller Inhalt", encoding="utf-8")
    store = KnowledgeStore()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({
        "documents": [{"document_id": "legacy-id", "path": str(source), "name": "alt.txt"}],
        "chunks": [{"document_id": "legacy-id", "text": "veraltet"}],
    }), encoding="utf-8")

    result = store.index_text_file(source)
    documents = store.list_documents()["documents"]

    assert result["indexed"] is True
    assert len(documents) == 1
    assert documents[0]["document_id"] != "legacy-id"
    assert all(chunk["document_id"] != "legacy-id" for chunk in store.get_document_chunks("legacy-id")["chunks"])


def test_malformed_entries_in_valid_json_are_ignored(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({
        "documents": ["not-a-document", {"document_id": "valid"}],
        "chunks": [123, {"document_id": "valid", "text": "Inhalt"}],
    }), encoding="utf-8")

    listed = store.list_documents()
    search = store.search_knowledge("Inhalt")

    assert listed["count"] == 1
    assert search["count"] == 1


def test_atomic_json_write_cleans_temporary_file_on_replace_failure(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "knowledge_index.json"

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(knowledge_store_module.os, "replace", fail_replace)

    try:
        knowledge_store_module._atomic_json_write(target, {"documents": [], "chunks": []})
    except OSError:
        pass
    else:
        raise AssertionError("atomic write should propagate the replace failure")

    assert not list(tmp_path.glob(".knowledge-*.tmp"))


def test_store_initialization_restores_pending_upload_still_referenced_by_index(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()
    document = store.store_upload("wiederherstellen.txt", b"wichtig")["document"]
    original = Path(document["path"])
    pending = store._pending_delete_path(original)
    store._write_pending_marker(pending, original, document["document_id"])
    pending.parent.mkdir(parents=True, exist_ok=True)
    original.replace(pending)

    KnowledgeStore()

    assert original.exists()
    assert not pending.exists()
    assert not store._pending_marker_path(pending).exists()


def test_store_initialization_finalizes_pending_upload_removed_from_index(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()
    document = store.store_upload("finalisieren.txt", b"loeschen")["document"]
    original = Path(document["path"])
    pending = store._pending_delete_path(original)
    store._write_pending_marker(pending, original, document["document_id"])
    pending.parent.mkdir(parents=True, exist_ok=True)
    original.replace(pending)
    data = store._load()
    data["documents"] = []
    store._save_unlocked(data)

    KnowledgeStore()

    assert not pending.exists()
    assert not store._pending_marker_path(pending).exists()


def test_pending_marker_outside_upload_directory_is_not_followed(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()
    outside = tmp_path / "outside.txt"
    outside.write_text("nicht anfassen", encoding="utf-8")
    pending = store.upload_dir / ".pending_delete" / "untrusted.pending"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text("pending", encoding="utf-8")
    store._pending_marker_path(pending).write_text(json.dumps({
        "pending_path": str(pending),
        "original_path": str(outside),
        "document_id": "outside",
    }), encoding="utf-8")

    KnowledgeStore()

    assert outside.exists()
    assert pending.exists()


def test_load_recovers_last_valid_backup_after_corrupt_primary(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    store = KnowledgeStore()
    valid_data = {"documents": [{"document_id": "known"}], "chunks": []}
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.backup_path.write_text(json.dumps(valid_data), encoding="utf-8")
    store.path.write_text("{not valid json", encoding="utf-8")

    loaded = store.list_documents()

    assert loaded["count"] == 1
    assert loaded["documents"][0]["document_id"] == "known"
    assert json.loads(store.path.read_text(encoding="utf-8"))["documents"][0]["document_id"] == "known"


def test_delete_local_path_removes_index_only_not_source_file(monkeypatch, tmp_path: Path) -> None:
    _configure_knowledge(monkeypatch, tmp_path)
    source = tmp_path / "docs" / "vertrag.txt"
    source.parent.mkdir()
    source.write_text("Kaufvertrag", encoding="utf-8")
    store = KnowledgeStore()
    indexed = store.index_text_file(source)

    result = store.delete_document(indexed["document"]["document_id"])

    assert result["deleted"] is True
    assert result["physical_file_deleted"] is False
    assert source.exists()
    assert store.list_documents()["count"] == 0


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
