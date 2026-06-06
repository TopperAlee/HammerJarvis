from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.assistant.orchestrator import AssistantOrchestrator
from app.assistant.session_state import session_state
from app.main import app


client = TestClient(app)


def _allowed_file(monkeypatch, tmp_path, name: str = "kaufvertrag.txt") -> Path:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    path = allowed / name
    path.write_text(
        "Kaufvertrag\nUVZ 123/2026\nKaufpreis 350.000 EUR\nKaeufer Alwin\nVerkaeufer Beispiel GmbH",
        encoding="utf-8",
    )
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(allowed))
    return path


def test_content_search_saves_last_results(monkeypatch, tmp_path) -> None:
    from app.tools.files.content_search_tool import ContentSearchTool

    session_state.clear()
    path = _allowed_file(monkeypatch, tmp_path)

    result = ContentSearchTool().search_file_contents("Kaufvertrag")

    assert result["count"] == 1
    assert session_state.get_best_file_result()["path"] == str(path)


def test_open_best_match_uses_last_result(monkeypatch, tmp_path) -> None:
    from app.assistant.session_state import open_best_match

    session_state.clear()
    path = _allowed_file(monkeypatch, tmp_path)
    session_state.save_file_results({"files": [{"path": str(path), "name": path.name}]})
    opened: list[str] = []
    monkeypatch.setattr("os.startfile", lambda value: opened.append(str(value)), raising=False)

    result = open_best_match()

    assert result["opened"] is True
    assert opened == [str(path)]


def test_open_result_by_index_works(monkeypatch, tmp_path) -> None:
    from app.assistant.session_state import open_result_by_index

    session_state.clear()
    first = _allowed_file(monkeypatch, tmp_path, "eins.txt")
    second = first.parent / "zwei.txt"
    second.write_text("Kaufvertrag zwei", encoding="utf-8")
    session_state.save_file_results({"files": [{"path": str(first)}, {"path": str(second)}]})
    opened: list[str] = []
    monkeypatch.setattr("os.startfile", lambda value: opened.append(str(value)), raising=False)

    result = open_result_by_index(2)

    assert result["opened"] is True
    assert opened == [str(second)]


def test_inspect_file_returns_text_preview(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_inspect_tool import FileInspectTool

    path = _allowed_file(monkeypatch, tmp_path)

    result = FileInspectTool().inspect_file(str(path))

    assert result["extraction_success"] is True
    assert result["filename"] == path.name
    assert "Kaufvertrag" in result["text_preview"]


def test_summarize_file_uses_mocked_llm(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_inspect_tool import FileInspectTool

    path = _allowed_file(monkeypatch, tmp_path)

    class FakeLLM:
        def is_available(self) -> bool:
            return True

        def create_response_with_tools(self, messages: list[dict[str, str]], tools: list[Any]) -> dict[str, str]:
            return {"text": "Zusammenfassung aus lokalem LLM."}

    result = FileInspectTool(llm_client=FakeLLM()).summarize_file(str(path), focus="Kaufvertrag")

    assert result["summary"] == "Zusammenfassung aus lokalem LLM."
    assert result["used_llm"] is True


def test_kaufvertrag_key_field_extraction_finds_uvz_and_price(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_inspect_tool import FileInspectTool

    path = _allowed_file(monkeypatch, tmp_path)

    result = FileInspectTool().extract_key_fields(str(path), document_type="kaufvertrag")

    assert "UVZ" in result["key_snippets"]
    assert "Kaufpreis" in result["key_snippets"]
    assert "350.000 EUR" in result["key_snippets"]["Kaufpreis"][0]


def test_file_inspect_blocks_outside_allowed_dirs(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_inspect_tool import FileInspectTool

    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    path = outside / "vertrag.txt"
    path.write_text("Kaufvertrag", encoding="utf-8")
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(allowed))

    result = FileInspectTool().inspect_file(str(path))

    assert result["blocked"] is True


def test_open_best_match_command_routes(monkeypatch, tmp_path) -> None:
    session_state.clear()
    path = _allowed_file(monkeypatch, tmp_path)
    session_state.save_file_results({"files": [{"path": str(path), "name": path.name}]})
    opened: list[str] = []
    monkeypatch.setattr("os.startfile", lambda value: opened.append(str(value)), raising=False)

    result = AssistantOrchestrator().handle_message("Jarvis, oeffne den besten Treffer")

    assert result["tool"] == "file_open_best_match"
    assert result["result"]["opened"] is True


def test_summarize_kaufvertrag_command_routes_after_search(monkeypatch, tmp_path) -> None:
    session_state.clear()
    path = _allowed_file(monkeypatch, tmp_path)
    session_state.save_file_results({"files": [{"path": str(path), "name": path.name}]})

    def fake_summarize(self: Any, path: str, focus: str | None = None) -> dict[str, Any]:
        return {"summary": "Kaufvertrag Zusammenfassung", "path": path, "used_llm": False}

    monkeypatch.setattr("app.tools.files.file_inspect_tool.FileInspectTool.summarize_file", fake_summarize)

    result = AssistantOrchestrator().handle_message("Jarvis, fasse den Kaufvertrag zusammen")

    assert result["tool"] == "file_summarize"
    assert "Kaufvertrag Zusammenfassung" in result["answer"]


def test_last_results_endpoint_returns_results(monkeypatch, tmp_path) -> None:
    session_state.clear()
    path = _allowed_file(monkeypatch, tmp_path)
    session_state.save_file_results({"files": [{"path": str(path), "name": path.name}]})

    response = client.get("/assistant/files/last-results")

    assert response.status_code == 200
    assert response.json()["files"][0]["path"] == str(path)
