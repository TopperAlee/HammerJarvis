from __future__ import annotations

from typing import Any

from hammer_jarvis.diagnostics.models import DiagnosticReport
from hammer_jarvis.documents.models import Document
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphNode
from hammer_jarvis.understanding.models import (
    EngineeringObjectType,
    UnderstandingRelationship,
    UnderstandingRelationshipType,
)
from hammer_jarvis.understanding.relationships import relationship_from_graph_edge, relationship_key


class RelationshipResolver:
    """Derives explainable read-only relationships from already available local data."""

    def resolve(
        self,
        graph: EngineeringGraph,
        *,
        diagnostics: DiagnosticReport | None = None,
        documents: list[Document] | None = None,
        knowledge_documents: list[dict[str, Any]] | None = None,
    ) -> list[UnderstandingRelationship]:
        relationships = [relationship_from_graph_edge(edge) for edge in graph.edges]
        relationships.extend(self._diagnostic_relationships(graph, diagnostics))
        relationships.extend(self._document_relationships(graph, documents or []))
        relationships.extend(self._knowledge_relationships(documents or [], knowledge_documents or []))
        return self._deduplicate(relationships)

    def _diagnostic_relationships(
        self,
        graph: EngineeringGraph,
        diagnostics: DiagnosticReport | None,
    ) -> list[UnderstandingRelationship]:
        if diagnostics is None:
            return []
        node_ids = {node.id for node in graph.nodes}
        relationships: list[UnderstandingRelationship] = []
        for issue in diagnostics.issues:
            if not issue.affected_object_id or issue.affected_object_id not in node_ids:
                continue
            relationships.append(
                UnderstandingRelationship(
                    source_id=f"diagnostic:{issue.id}",
                    target_id=issue.affected_object_id,
                    type=UnderstandingRelationshipType.AFFECTS,
                    evidence=[
                        "Diagnostic Issue referenziert affected_object_id.",
                        f"Regel: {issue.rule_id}.",
                    ],
                    metadata={
                        "source": "diagnostics",
                        "severity": issue.severity,
                        "category": issue.category,
                        "read_only": issue.read_only,
                    },
                )
            )
        return relationships

    def _document_relationships(
        self,
        graph: EngineeringGraph,
        documents: list[Document],
    ) -> list[UnderstandingRelationship]:
        project = _first_node_of_type(graph, EngineeringObjectType.PROJECT)
        if project is None:
            return []
        return [
            UnderstandingRelationship(
                source_id=project.id,
                target_id=document.id,
                type=UnderstandingRelationshipType.CONTAINS,
                evidence=[
                    "Document Intelligence Store ist im selben lokalen Engineering-Kontext verfuegbar.",
                    "Project-Knoten wurde aus dem aktiven Engineering Graph gelesen.",
                ],
                metadata={
                    "source": "document_intelligence",
                    "document_id": document.id,
                    "filename": document.filename,
                    "document_type": document.type,
                },
            )
            for document in documents
        ]

    def _knowledge_relationships(
        self,
        documents: list[Document],
        knowledge_documents: list[dict[str, Any]],
    ) -> list[UnderstandingRelationship]:
        by_name = {document.filename.lower(): document for document in documents}
        by_path = {document.path.lower(): document for document in documents}
        relationships: list[UnderstandingRelationship] = []
        for item in knowledge_documents:
            name = str(item.get("name") or "").lower()
            path = str(item.get("path") or "").lower()
            document = by_path.get(path) or by_name.get(name)
            if document is None:
                continue
            knowledge_id = str(item.get("document_id") or f"knowledge:{document.id}")
            relationships.append(
                UnderstandingRelationship(
                    source_id=knowledge_id,
                    target_id=document.id,
                    type=UnderstandingRelationshipType.REFERENCES,
                    evidence=[
                        "Knowledge-Dokument und Document-Intelligence-Dokument teilen Pfad oder Dateiname.",
                        "Beziehung basiert auf vorhandenen lokalen Metadaten.",
                    ],
                    metadata={"source": "knowledge_store"},
                )
            )
        return relationships

    def _deduplicate(self, relationships: list[UnderstandingRelationship]) -> list[UnderstandingRelationship]:
        deduplicated: dict[tuple[str, str, str], UnderstandingRelationship] = {}
        for relationship in relationships:
            deduplicated.setdefault(relationship_key(relationship), relationship)
        return list(deduplicated.values())


def _first_node_of_type(graph: EngineeringGraph, node_type: str) -> GraphNode | None:
    return next((node for node in graph.nodes if node.type == node_type), None)
