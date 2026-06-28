from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from hammer_jarvis.engineering.classifier.protool import ProjectFileType, ProToolClassifier
from hammer_jarvis.engineering.importer.project_importer import ProjectImporter
from hammer_jarvis.engineering.scanner.filesystem import ProjectScanner
from hammer_jarvis.engineering.tree import EngineeringTreeBuilder


client = TestClient(app)


def _project_dir(tmp_path: Path) -> Path:
    root = tmp_path / "ProToolProject"
    root.mkdir()
    for name in ["MessageText.csv", "AlarmText.csv", "Variables.csv", "InfoHelpText.csv", "ignored.exe"]:
        (root / name).write_text("demo", encoding="utf-8")
    hidden = root / ".git"
    hidden.mkdir()
    (hidden / "MessageText.csv").write_text("ignore", encoding="utf-8")
    cache = root / "__pycache__"
    cache.mkdir()
    (cache / "AlarmText.csv").write_text("ignore", encoding="utf-8")
    nested = root / "Nested"
    nested.mkdir()
    (nested / "RecipeText.csv").write_text("demo", encoding="utf-8")
    return root


def test_protool_classifier_recognizes_known_csv_names() -> None:
    classifier = ProToolClassifier()

    assert classifier.classify("MessageText.csv") == ProjectFileType.MESSAGE_TEXT
    assert classifier.classify("AlarmText.csv") == ProjectFileType.ALARM_TEXT
    assert classifier.classify("InfoHelpText.csv") == ProjectFileType.INFO_TEXT
    assert classifier.classify("TextList.csv") == ProjectFileType.TEXT_LIST
    assert classifier.classify("RecipeText.csv") == ProjectFileType.RECIPE
    assert classifier.classify("Variables.csv") == ProjectFileType.VARIABLES
    assert classifier.classify("Other.csv") == ProjectFileType.UNKNOWN


def test_project_scanner_scans_allowed_files_without_opening_contents(tmp_path: Path, monkeypatch) -> None:
    root = _project_dir(tmp_path)
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(tmp_path))

    result = ProjectScanner(max_depth=2, max_files=20).scan(root)
    names = [file.path.name for file in result.files]

    assert "MessageText.csv" in names
    assert "AlarmText.csv" in names
    assert "Variables.csv" in names
    assert "RecipeText.csv" in names
    assert "ignored.exe" not in names
    assert all(".git" not in str(file.path) for file in result.files)
    assert all("__pycache__" not in str(file.path) for file in result.files)


def test_project_scanner_rejects_path_outside_allowed_dirs(tmp_path: Path, monkeypatch) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(allowed))

    try:
        ProjectScanner().scan(outside)
    except ValueError as exc:
        assert "ausserhalb" in str(exc) or "außerhalb" in str(exc)
    else:
        raise AssertionError("Expected path safety rejection")


def test_project_importer_builds_project_files_and_graph_nodes(tmp_path: Path, monkeypatch) -> None:
    root = _project_dir(tmp_path)
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(tmp_path))
    scan_result = ProjectScanner(max_depth=2, max_files=20).scan(root)

    imported = ProjectImporter().import_scan(scan_result)

    assert imported.project.name == "ProToolProject"
    assert any(file.name == "MessageText.csv" and file.kind == "MESSAGE_TEXT" for file in imported.project.files)
    assert any(node.type == "ProjectFile" and node.name == "MessageText.csv" for node in imported.graph.nodes)
    assert any(edge.type == "CONTAINS" for edge in imported.graph.edges)
    assert all(node.type in {"Project", "ProjectFile"} for node in imported.graph.nodes)


def test_engineering_tree_builder_returns_json_compatible_tree(tmp_path: Path, monkeypatch) -> None:
    root = _project_dir(tmp_path)
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(tmp_path))
    imported = ProjectImporter().import_scan(ProjectScanner(max_depth=2, max_files=20).scan(root))

    tree = EngineeringTreeBuilder().build(imported.project)

    assert tree["name"] == "ProToolProject"
    assert tree["type"] == "Project"
    assert "children" in tree
    assert any(child["name"] == "MessageText.csv" for child in tree["children"])


def test_engineering_project_open_and_read_endpoints(tmp_path: Path, monkeypatch) -> None:
    root = _project_dir(tmp_path)
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(tmp_path))

    open_response = client.post("/assistant/engineering/projects/open", json={"path": str(root)})

    assert open_response.status_code == 200
    opened = open_response.json()
    assert opened["project_name"] == "ProToolProject"
    assert opened["file_count"] >= 4

    project_id = opened["project_id"]
    project_response = client.get(f"/assistant/engineering/projects/{project_id}")
    tree_response = client.get(f"/assistant/engineering/projects/{project_id}/tree")
    files_response = client.get(f"/assistant/engineering/projects/{project_id}/files")

    assert project_response.status_code == 200
    assert tree_response.status_code == 200
    assert files_response.status_code == 200
    assert any(file["kind"] == "MESSAGE_TEXT" for file in files_response.json()["files"])


def test_engineering_project_unknown_id_returns_404() -> None:
    response = client.get("/assistant/engineering/projects/missing-project")

    assert response.status_code == 404


def test_engineering_project_open_rejects_invalid_body() -> None:
    response = client.post("/assistant/engineering/projects/open", json={"path": ""})

    assert response.status_code == 422


def test_dashboard_contains_project_explorer_open_controls() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'id="engineeringProjectPath"' in html
    assert 'id="engineeringOpenProject"' in html
    assert "Projekt öffnen" in html
    assert "Projekt laden" in html
    assert "/assistant/engineering/projects/open" in js
    assert "Analyse verfügbar" in js

