from pathlib import Path

from fastapi.testclient import TestClient

from app.assistant.performance.metrics_store import metrics_store
from app.assistant.performance.timing import time_operation
from app.main import app
from app.tools.files.file_search_tool import FileSearchTool


client = TestClient(app)


def test_performance_status_endpoint_returns_summary(monkeypatch) -> None:
    monkeypatch.setenv("PERFORMANCE_METRICS_ENABLED", "true")
    with time_operation("test.operation", "test"):
        pass

    response = client.get("/assistant/performance/status")

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["summary"]["count"] >= 1


def test_performance_benchmark_endpoint_returns_checks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORY_FILE", str(tmp_path / "memory.json"))
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setenv("LLM_ENABLED", "false")

    response = client.get("/assistant/performance/benchmark")

    assert response.status_code == 200
    assert response.json()["summary"]["count"] >= 4


def test_file_search_skips_configured_heavy_folders(monkeypatch, tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    node_modules = allowed / "node_modules"
    normal = allowed / "docs"
    node_modules.mkdir(parents=True)
    normal.mkdir(parents=True)
    (node_modules / "target.txt").write_text("ignored", encoding="utf-8")
    (normal / "target.txt").write_text("found", encoding="utf-8")
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(allowed))
    monkeypatch.setenv("FILE_SEARCH_MAX_DEPTH", "12")

    result = FileSearchTool().search_files("target")

    assert result["count"] == 1
    assert "docs" in result["files"][0]["path"]
    assert any("node_modules" in skipped for skipped in result["skipped_dirs"])


def test_file_search_respects_max_depth(monkeypatch, tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    shallow = allowed / "one"
    deep = allowed / "one" / "two"
    shallow.mkdir(parents=True)
    deep.mkdir(parents=True)
    (shallow / "target.txt").write_text("found", encoding="utf-8")
    (deep / "target_deep.txt").write_text("ignored", encoding="utf-8")
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(allowed))
    monkeypatch.setenv("FILE_SEARCH_MAX_DEPTH", "1")

    result = FileSearchTool().search_files("target")

    assert result["count"] == 1
    assert result["files"][0]["name"] == "target.txt"
