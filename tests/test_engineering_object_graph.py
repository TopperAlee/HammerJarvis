from dataclasses import asdict

from fastapi.testclient import TestClient

from app.main import app
from hammer_jarvis.engineering.graph import GraphBuilder, GraphEdge, GraphNode


client = TestClient(app)


def test_graph_node_and_edge_are_json_compatible() -> None:
    node = GraphNode(
        id="node-1",
        type="TextResource",
        name="Hydraulikpumpe überprüfen",
        source_file="MessageText.csv",
        source_line=2,
        metadata={"language": "de"},
    )
    edge = GraphEdge(
        source_id="file-1",
        target_id="node-1",
        type="DEFINES",
        metadata={"parser": "demo"},
    )

    assert asdict(node)["metadata"]["language"] == "de"
    assert asdict(edge)["type"] == "DEFINES"


def test_demo_graph_contains_project_file_and_text_resource() -> None:
    graph = GraphBuilder().build_demo_graph("demo-project")
    node_types = {node.type for node in graph.nodes}

    assert {"Project", "ProjectFile", "TextResource"} <= node_types
    assert graph.get_node("project:demo-project").name == "Beispielprojekt"
    assert graph.get_node("file:demo-project:MessageText.csv").name == "MessageText.csv"
    assert graph.get_node("text:demo-project:hydraulikpumpe").name == "Hydraulikpumpe überprüfen"


def test_graph_search_finds_file_and_text_resource() -> None:
    graph = GraphBuilder().build_demo_graph("demo-project")

    file_results = graph.search("MessageText.csv")
    text_results = graph.search("Hydraulikpumpe")

    assert file_results[0].id == "file:demo-project:MessageText.csv"
    assert text_results[0].id == "text:demo-project:hydraulikpumpe"


def test_graph_impact_returns_direct_neighbors() -> None:
    graph = GraphBuilder().build_demo_graph("demo-project")

    impact = graph.impact("file:demo-project:MessageText.csv")
    neighbor_ids = {node.id for node in impact}

    assert "project:demo-project" in neighbor_ids
    assert "text:demo-project:hydraulikpumpe" in neighbor_ids


def test_engineering_graph_project_endpoint_returns_demo_graph() -> None:
    response = client.get("/assistant/engineering/graph/projects/demo-project")

    assert response.status_code == 200
    payload = response.json()
    assert any(node["type"] == "Project" for node in payload["nodes"])
    assert any(edge["type"] == "CONTAINS" for edge in payload["edges"])


def test_engineering_graph_node_endpoint_returns_node() -> None:
    response = client.get("/assistant/engineering/graph/nodes/text:demo-project:hydraulikpumpe")

    assert response.status_code == 200
    assert response.json()["name"] == "Hydraulikpumpe überprüfen"


def test_engineering_graph_search_endpoint_returns_matches() -> None:
    response = client.get("/assistant/engineering/graph/search", params={"q": "MessageText.csv"})

    assert response.status_code == 200
    assert response.json()["results"][0]["name"] == "MessageText.csv"


def test_engineering_graph_impact_endpoint_returns_neighbors() -> None:
    response = client.get("/assistant/engineering/graph/impact/file:demo-project:MessageText.csv")

    assert response.status_code == 200
    neighbor_ids = {node["id"] for node in response.json()["nodes"]}
    assert "text:demo-project:hydraulikpumpe" in neighbor_ids


def test_engineering_graph_unknown_project_returns_404() -> None:
    response = client.get("/assistant/engineering/graph/projects/unknown")

    assert response.status_code == 404


def test_engineering_graph_unknown_node_returns_404() -> None:
    response = client.get("/assistant/engineering/graph/nodes/unknown")

    assert response.status_code == 404


def test_engineering_graph_empty_search_returns_400() -> None:
    response = client.get("/assistant/engineering/graph/search", params={"q": "   "})

    assert response.status_code == 400

