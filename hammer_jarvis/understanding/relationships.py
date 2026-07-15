from __future__ import annotations

from hammer_jarvis.engineering.graph import GraphEdge
from hammer_jarvis.understanding.models import UnderstandingRelationship


def relationship_from_graph_edge(edge: GraphEdge) -> UnderstandingRelationship:
    return UnderstandingRelationship(
        source_id=edge.source_id,
        target_id=edge.target_id,
        type=edge.type,
        evidence=[
            "Bestehende Engineering-Graph-Edge.",
            f"Graph-Edge-Typ: {edge.type}.",
        ],
        metadata={"source": "engineering_graph", **edge.metadata},
    )


def relationship_key(relationship: UnderstandingRelationship) -> tuple[str, str, str]:
    return (relationship.source_id, relationship.target_id, relationship.type)
