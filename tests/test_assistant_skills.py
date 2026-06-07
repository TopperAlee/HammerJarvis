from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.assistant.orchestrator import AssistantOrchestrator
from app.assistant.skills.skill_registry import SkillRegistry
from app.assistant.tool_registry import ToolRegistry
from app.main import app


client = TestClient(app)


def _configure_dirs(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    allowed = tmp_path / "allowed"
    exports = tmp_path / "exports"
    allowed.mkdir()
    exports.mkdir()
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(allowed))
    monkeypatch.setenv("EXPORT_DIR", str(exports))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    return allowed, exports


def test_skill_registry_lists_all_skills() -> None:
    skills = SkillRegistry().list_skills()["skills"]
    names = {skill["name"] for skill in skills}

    assert {
        "document_summarize",
        "document_extract_key_fields",
        "file_search_report",
        "web_research_report",
        "web_research_excel",
        "document_index_excel",
    }.issubset(names)


def test_document_summarize_blocks_unsafe_path() -> None:
    result = SkillRegistry().execute("document_summarize", {"path": "../secret.txt"})

    assert result["blocked"] is True
    assert result["risk"] == "GREEN"


def test_document_summarize_works_with_mocked_llm(monkeypatch, tmp_path: Path) -> None:
    allowed, _exports = _configure_dirs(monkeypatch, tmp_path)
    document = allowed / "vertrag.txt"
    document.write_text("Dies ist ein kurzer Kaufvertrag mit Kaufpreis 100 Euro.", encoding="utf-8")

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr("app.assistant.llm_client.LLMClient.is_available", lambda self: True)
    monkeypatch.setattr(
        "app.assistant.llm_client.LLMClient.create_response_with_tools",
        lambda self, messages, tools: {"text": "Mock-Zusammenfassung aus lokalem LLM."},
    )

    result = SkillRegistry().execute("document_summarize", {"path": str(document)})

    assert result["skill"] == "document_summarize"
    assert result["summary"] == "Mock-Zusammenfassung aus lokalem LLM."
    assert result["file"]["filename"] == "vertrag.txt"


def test_key_field_extraction_does_not_invent_missing_fields(monkeypatch, tmp_path: Path) -> None:
    allowed, _exports = _configure_dirs(monkeypatch, tmp_path)
    document = allowed / "kaufvertrag.txt"
    document.write_text("Kaufvertrag UVZ 123/2026 Notar Beispielstadt", encoding="utf-8")

    result = SkillRegistry().execute(
        "document_extract_key_fields",
        {"path": str(document), "document_type": "kaufvertrag"},
    )

    assert result["fields"]["uvz"]["value"] != "nicht gefunden"
    assert "UVZ" in result["fields"]["uvz"]["snippet"]
    assert result["fields"]["kaufpreis"]["value"] == "nicht gefunden"


def test_file_search_report_creates_markdown(monkeypatch, tmp_path: Path) -> None:
    allowed, exports = _configure_dirs(monkeypatch, tmp_path)
    (allowed / "hauskauf.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

    result = SkillRegistry().execute(
        "file_search_report",
        {"query": "Hauskauf", "extensions": [".pdf"], "content_search": False},
    )

    assert result["created"] is True
    assert result["file_type"] == "md"
    assert Path(result["path"]).is_relative_to(exports)
    assert "hauskauf.pdf" in Path(result["path"]).read_text(encoding="utf-8")


def test_document_index_creates_excel(monkeypatch, tmp_path: Path) -> None:
    allowed, exports = _configure_dirs(monkeypatch, tmp_path)
    (allowed / "hauskauf.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

    result = SkillRegistry().execute(
        "document_index_excel",
        {"query": "Hauskauf", "extensions": [".pdf"]},
    )

    assert result["created"] is True
    assert Path(result["path"]).is_relative_to(exports)
    workbook = load_workbook(result["path"])
    headers = [cell.value for cell in workbook.active[1]]
    workbook.close()
    assert headers[:4] == ["Dateiname", "Pfad", "Typ", "Größe"]


def test_web_report_uses_only_source_urls_from_tool(monkeypatch, tmp_path: Path) -> None:
    _allowed, exports = _configure_dirs(monkeypatch, tmp_path)
    original_execute = ToolRegistry.execute_tool

    def fake_execute(self: Any, name: str, arguments: dict[str, Any], confirm: bool = False) -> dict[str, Any]:
        if name == "web_research":
            return {
                "executed": True,
                "risk": "GREEN",
                "result": {
                    "query": "Graph",
                    "summary": "Microsoft Graph Search Dokumentation.",
                    "confidence": "hoch",
                    "limitations": "Nur Quellenliste.",
                    "sources": [
                        {
                            "title": "Microsoft Learn",
                            "url": "https://learn.microsoft.com/graph/search",
                            "domain": "learn.microsoft.com",
                            "source_quality": "official",
                            "snippet": "Graph Search",
                        }
                    ],
                },
            }
        return original_execute(self, name, arguments, confirm)

    monkeypatch.setattr("app.assistant.tool_registry.ToolRegistry.execute_tool", fake_execute)

    result = SkillRegistry().execute("web_research_report", {"query": "Graph"})
    content = Path(result["path"]).read_text(encoding="utf-8")

    assert Path(result["path"]).is_relative_to(exports)
    assert "https://learn.microsoft.com/graph/search" in content
    assert "example.com" not in content


def test_web_research_excel_creates_xlsx(monkeypatch, tmp_path: Path) -> None:
    _allowed, exports = _configure_dirs(monkeypatch, tmp_path)
    original_execute = ToolRegistry.execute_tool

    def fake_execute(self: Any, name: str, arguments: dict[str, Any], confirm: bool = False) -> dict[str, Any]:
        if name == "web_research":
            return {
                "executed": True,
                "risk": "GREEN",
                "result": {
                    "query": "Graph",
                    "confidence": "hoch",
                    "sources": [
                        {
                            "title": "Microsoft Learn",
                            "url": "https://learn.microsoft.com/graph/search",
                            "domain": "learn.microsoft.com",
                            "source_quality": "official",
                            "snippet": "Graph Search",
                        }
                    ],
                },
            }
        return original_execute(self, name, arguments, confirm)

    monkeypatch.setattr("app.assistant.tool_registry.ToolRegistry.execute_tool", fake_execute)

    result = SkillRegistry().execute("web_research_excel", {"query": "Graph"})

    assert result["created"] is True
    assert result["file_type"] == "xlsx"
    assert Path(result["path"]).is_relative_to(exports)


def test_skill_endpoints_return_200(monkeypatch, tmp_path: Path) -> None:
    allowed, _exports = _configure_dirs(monkeypatch, tmp_path)
    document = allowed / "notiz.txt"
    document.write_text("Lokaler Testinhalt", encoding="utf-8")

    response = client.post(
        "/assistant/skills/document/summarize",
        json={"path": str(document), "focus": "Test"},
    )

    assert response.status_code == 200
    assert response.json()["skill"] == "document_summarize"


def test_orchestrator_routes_document_index_excel(monkeypatch, tmp_path: Path) -> None:
    allowed, _exports = _configure_dirs(monkeypatch, tmp_path)
    (allowed / "hauskauf.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

    result = AssistantOrchestrator().handle_message(
        "Jarvis, erstelle eine Excel-Übersicht der Hauskauf-Dokumente"
    )

    assert result["tool"] == "document_index_excel"
    assert result["result"]["created"] is True
    assert "keine Excel" not in result["answer"]


def test_orchestrator_routes_web_research_excel(monkeypatch, tmp_path: Path) -> None:
    _allowed, _exports = _configure_dirs(monkeypatch, tmp_path)
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "false")

    result = AssistantOrchestrator().handle_message(
        "Jarvis, recherchiere Microsoft Graph und erstelle eine Excel mit Quellen"
    )

    assert result["tool"] == "web_research_excel"
    assert result["result"]["created"] is True
