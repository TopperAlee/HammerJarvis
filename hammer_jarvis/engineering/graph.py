from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphNode:
    id: str
    type: str
    name: str
    source_file: str | None
    source_line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineeringGraph:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def get_node(self, node_id: str) -> GraphNode | None:
        return next((node for node in self.nodes if node.id == node_id), None)

    def search(self, query: str) -> list[GraphNode]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []
        return [
            node
            for node in self.nodes
            if normalized_query in node.name.lower()
            or normalized_query in node.id.lower()
            or normalized_query in (node.source_file or "").lower()
            or any(normalized_query in str(value).lower() for value in node.metadata.values())
        ]

    def neighbors(self, node_id: str) -> list[GraphNode]:
        neighbor_ids: set[str] = set()
        for edge in self.edges:
            if edge.source_id == node_id:
                neighbor_ids.add(edge.target_id)
            if edge.target_id == node_id:
                neighbor_ids.add(edge.source_id)
        return [node for node in self.nodes if node.id in neighbor_ids]

    def impact(self, node_id: str) -> list[GraphNode]:
        return self.neighbors(node_id)


class GraphBuilder:
    def build_demo_graph(self, project_id: str = "demo-project") -> EngineeringGraph:
        if project_id != "demo-project":
            raise ValueError(f"Unknown engineering demo project: {project_id}")

        project = GraphNode(
            id="project:demo-project",
            type="Project",
            name="Beispielprojekt",
            source_file=None,
            metadata={"module": "engineering"},
        )
        message_file = GraphNode(
            id="file:demo-project:MessageText.csv",
            type="ProjectFile",
            name="MessageText.csv",
            source_file="MessageText.csv",
            metadata={"kind": "hmi_text", "module": "protool"},
        )
        text_resource = GraphNode(
            id="text:demo-project:hydraulikpumpe",
            type="TextResource",
            name="Hydraulikpumpe überprüfen",
            source_file="MessageText.csv",
            source_line=2,
            metadata={"language": "de", "panel": "OP7"},
        )
        return EngineeringGraph(
            nodes=[project, message_file, text_resource],
            edges=[
                GraphEdge(
                    source_id=project.id,
                    target_id=message_file.id,
                    type="CONTAINS",
                    metadata={"source": "demo"},
                ),
                GraphEdge(
                    source_id=message_file.id,
                    target_id=text_resource.id,
                    type="DEFINES",
                    metadata={"source": "demo"},
                ),
            ],
        )

