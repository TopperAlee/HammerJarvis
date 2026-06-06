from pathlib import Path

from fastapi.testclient import TestClient

from app.assistant.orchestrator import AssistantOrchestrator
from app.main import app
from app.tools.files.file_creator import FileCreatorTool
from app.tools.files.path_safety import normalize_user_path


client = TestClient(app)


def _create_export(monkeypatch, tmp_path, filename: str = "ausgaben.xlsx") -> Path:
    export_dir = tmp_path / "exports"
    monkeypatch.setenv("EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(export_dir))
    result = FileCreatorTool().create_excel_file(
        "Ausgaben",
        [{"name": "Ausgaben", "headers": ["Datum"], "rows": []}],
        filename=filename,
    )
    return Path(result["path"])


def test_search_finds_created_ausgaben_xlsx_in_exports(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_search_tool import FileSearchTool

    _create_export(monkeypatch, tmp_path)

    result = FileSearchTool().search_files("ausgaben")

    assert result["count"] == 1
    assert result["files"][0]["name"] == "ausgaben.xlsx"
    assert result["files"][0]["extension"] == ".xlsx"


def test_search_respects_extension_filter(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_search_tool import FileSearchTool

    _create_export(monkeypatch, tmp_path)
    (tmp_path / "exports" / "ausgaben.md").write_text("# Ausgaben", encoding="utf-8")

    result = FileSearchTool().search_files("ausgaben", extensions=[".xlsx"])

    assert result["count"] == 1
    assert result["files"][0]["name"] == "ausgaben.xlsx"


def test_search_does_not_search_outside_allowed_dirs(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_search_tool import FileSearchTool

    export_dir = tmp_path / "exports"
    outside_dir = tmp_path / "outside"
    export_dir.mkdir()
    outside_dir.mkdir()
    monkeypatch.setenv("EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(export_dir))
    (outside_dir / "ausgaben.xlsx").write_text("outside", encoding="utf-8")

    result = FileSearchTool().search_files("ausgaben")

    assert result["count"] == 0


def test_path_traversal_is_blocked(monkeypatch, tmp_path) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(export_dir))

    try:
        normalize_user_path("..\\secret.txt")
    except ValueError as exc:
        assert "Pfad" in str(exc) or "ungueltig" in str(exc).lower()
    else:
        raise AssertionError("path traversal must fail")


def test_open_allowed_file_uses_startfile(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_open_tool import FileOpenTool

    file_path = _create_export(monkeypatch, tmp_path)
    opened: list[str] = []
    monkeypatch.setattr("os.startfile", lambda path: opened.append(str(path)), raising=False)

    result = FileOpenTool().open_file(str(file_path))

    assert result["opened"] is True
    assert opened == [str(file_path)]


def test_open_outside_allowed_dirs_is_blocked(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_open_tool import FileOpenTool

    export_dir = tmp_path / "exports"
    outside_dir = tmp_path / "outside"
    export_dir.mkdir()
    outside_dir.mkdir()
    file_path = outside_dir / "secret.txt"
    file_path.write_text("secret", encoding="utf-8")
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(export_dir))

    result = FileOpenTool().open_file(str(file_path))

    assert result["opened"] is False
    assert result["blocked"] is True


def test_open_latest_export_works(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_open_tool import FileOpenTool

    first = _create_export(monkeypatch, tmp_path, "alt.xlsx")
    latest = _create_export(monkeypatch, tmp_path, "neu.xlsx")
    first.touch()
    latest.touch()
    opened: list[str] = []
    monkeypatch.setattr("os.startfile", lambda path: opened.append(str(path)), raising=False)

    result = FileOpenTool().open_latest_export()

    assert result["opened"] is True
    assert Path(result["path"]).name in {"neu.xlsx", "alt.xlsx"}
    assert opened


def test_file_search_endpoint_returns_200(monkeypatch, tmp_path) -> None:
    _create_export(monkeypatch, tmp_path)

    response = client.get("/assistant/files/search", params={"q": "ausgaben", "extension": ".xlsx"})

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_file_recent_endpoint_returns_200(monkeypatch, tmp_path) -> None:
    _create_export(monkeypatch, tmp_path)

    response = client.get("/assistant/files/recent")

    assert response.status_code == 200
    assert response.json()["count"] >= 1


def test_file_status_endpoint_returns_200(monkeypatch, tmp_path) -> None:
    onedrive_dir = tmp_path / "OneDrive"
    onedrive_dir.mkdir()
    monkeypatch.setenv("OneDrive", str(onedrive_dir))
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(onedrive_dir))

    response = client.get("/assistant/files/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["onedrive_env"] == str(onedrive_dir)
    assert payload["onedrive_configured"] is True


def test_onedrive_env_detected_but_not_auto_configured(monkeypatch, tmp_path) -> None:
    onedrive_dir = tmp_path / "OneDrive"
    export_dir = tmp_path / "exports"
    onedrive_dir.mkdir()
    export_dir.mkdir()
    monkeypatch.setenv("OneDrive", str(onedrive_dir))
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(export_dir))

    response = client.get("/assistant/files/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["onedrive_env"] == str(onedrive_dir)
    assert payload["onedrive_configured"] is False


def test_file_open_endpoint_blocks_unsafe_path(monkeypatch, tmp_path) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(export_dir))

    response = client.post("/assistant/files/open", json={"path": "..\\secret.txt"})

    assert response.status_code == 200
    assert response.json()["blocked"] is True


def test_find_expenses_excel_routes_to_file_search(monkeypatch, tmp_path) -> None:
    _create_export(monkeypatch, tmp_path)

    result = AssistantOrchestrator().handle_message("Jarvis, finde die Excel mit meinen Ausgaben.")

    assert result["tool"] == "file_search"
    assert result["result"]["count"] == 1


def test_open_latest_created_file_routes_to_open_latest(monkeypatch, tmp_path) -> None:
    _create_export(monkeypatch, tmp_path)
    opened: list[str] = []
    monkeypatch.setattr("os.startfile", lambda path: opened.append(str(path)), raising=False)

    result = AssistantOrchestrator().handle_message("Jarvis, öffne die letzte erstellte Datei.")

    assert result["tool"] == "file_open_latest_export"
    assert result["result"]["opened"] is True
    assert opened


def test_onedrive_search_routes_to_file_search(monkeypatch, tmp_path) -> None:
    onedrive_dir = tmp_path / "OneDrive"
    onedrive_dir.mkdir()
    monkeypatch.setenv("OneDrive", str(onedrive_dir))
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(onedrive_dir))
    (onedrive_dir / "Mietvertrag.pdf").write_text("vertrag", encoding="utf-8")

    result = AssistantOrchestrator().handle_message("Jarvis, suche in OneDrive nach Mietvertrag")

    assert result["tool"] == "file_search"
    assert result["result"]["count"] == 1
    assert result["result"]["files"][0]["name"] == "Mietvertrag.pdf"


def test_onedrive_not_configured_response_explains_configuration(monkeypatch, tmp_path) -> None:
    onedrive_dir = tmp_path / "OneDrive"
    export_dir = tmp_path / "exports"
    onedrive_dir.mkdir()
    export_dir.mkdir()
    monkeypatch.setenv("OneDrive", str(onedrive_dir))
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(export_dir))

    result = AssistantOrchestrator().handle_message("Jarvis, suche in OneDrive nach Mietvertrag")

    assert result["tool"] == "file_search_status"
    assert "OneDrive ist lokal noch nicht als Suchordner konfiguriert" in result["answer"]
    assert "FILE_SEARCH_ALLOWED_DIRS" in result["answer"]


def test_onedrive_allowed_folder_search_finds_file(monkeypatch, tmp_path) -> None:
    from app.tools.files.file_search_tool import FileSearchTool

    onedrive_dir = tmp_path / "OneDrive"
    onedrive_dir.mkdir()
    (onedrive_dir / "Mietvertrag.pdf").write_text("vertrag", encoding="utf-8")
    monkeypatch.setenv("OneDrive", str(onedrive_dir))
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(onedrive_dir))

    result = FileSearchTool().search_files("Mietvertrag")

    assert result["count"] == 1
    assert result["files"][0]["name"] == "Mietvertrag.pdf"


def test_onedrive_search_never_returns_generic_unsupported_answer(monkeypatch, tmp_path) -> None:
    onedrive_dir = tmp_path / "OneDrive"
    onedrive_dir.mkdir()
    monkeypatch.setenv("OneDrive", str(onedrive_dir))
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(onedrive_dir))

    result = AssistantOrchestrator().handle_message("Jarvis, suche in OneDrive nach Mietvertrag")

    assert "keine direkte Suche in OneDrive" not in result["answer"]
    assert "unterstuetze" not in result["answer"].lower()
    assert result["tool"] == "file_search"
