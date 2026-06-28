from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from hammer_jarvis.engineering.models import Project, ProjectFile, TextResource, Variable
from hammer_jarvis.engineering.plugins import get_engineering_modules


client = TestClient(app)


def test_engineering_project_models_are_serializable() -> None:
    project = Project(
        id="demo",
        name="Beispielprojekt",
        files=[
            ProjectFile(name="MessageText.csv", path=None, kind="hmi_text"),
            ProjectFile(name="Variables.csv", path=None, kind="variables"),
        ],
        variables=[Variable(name="Motor_Start", data_type="Bool")],
        text_resources=[TextResource(key="M001", text="Motor bereit", language="de")],
    )

    data = asdict(project)

    assert data["name"] == "Beispielprojekt"
    assert data["files"][0]["name"] == "MessageText.csv"
    assert data["variables"][0]["data_type"] == "Bool"
    assert data["text_resources"][0]["text"] == "Motor bereit"


def test_engineering_plugin_registry_lists_future_modules() -> None:
    modules = get_engineering_modules()
    module_ids = [module["id"] for module in modules]

    assert module_ids == ["protool", "wincc_flexible", "tia", "step7", "translator", "diagnostics"]
    assert modules[0] == {"id": "protool", "name": "ProTool Assistant", "status": "available"}
    assert all("status" in module for module in modules)


def test_engineering_modules_endpoint_returns_registry() -> None:
    response = client.get("/assistant/engineering/modules")

    assert response.status_code == 200
    modules = response.json()
    assert modules[0]["id"] == "protool"
    assert modules[0]["status"] == "available"
    assert {module["id"] for module in modules} >= {"wincc_flexible", "tia", "step7"}


def test_engineering_projects_endpoint_returns_demo_project() -> None:
    response = client.get("/assistant/engineering/projects")

    assert response.status_code == 200
    projects = response.json()
    assert projects[0]["name"] == "Beispielprojekt"
    assert [item["name"] for item in projects[0]["files"]] == [
        "MessageText.csv",
        "AlarmText.csv",
        "Variables.csv",
        "HelpText.csv",
        "Recipes.csv",
    ]


def test_dashboard_renders_engineering_workspace() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    css = Path("app/static/dashboard.css").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'href="#engineering"' in html
    assert 'id="engineering"' in html
    assert "Project Explorer" in html
    for label in ["Projekte", "HMI", "PLC", "Übersetzung", "Dokumentation"]:
        assert label in html
    for file_name in ["MessageText.csv", "AlarmText.csv", "Variables.csv", "HelpText.csv", "Recipes.csv"]:
        assert file_name in html
    assert ".engineering-workspace" in css
    assert "engineeringProjectExplorer" in js
    assert "engineeringModules" in js

