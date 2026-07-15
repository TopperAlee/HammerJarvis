from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from hammer_jarvis.diagnostics.models import DiagnosticReport
from hammer_jarvis.documents.models import Document
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphNode
from hammer_jarvis.understanding.models import EngineeringObjectType, EngineeringUnderstandingReport
from hammer_jarvis.understanding.resolver import RelationshipResolver


class EngineeringUnderstandingEngine:
    """Builds a deterministic read-only understanding report from local graph data."""

    def __init__(self, resolver: RelationshipResolver | None = None) -> None:
        self.resolver = resolver or RelationshipResolver()

    def build(
        self,
        graph: EngineeringGraph,
        *,
        diagnostics: DiagnosticReport | None = None,
        documents: list[Document] | None = None,
        knowledge_documents: list[dict[str, Any]] | None = None,
    ) -> EngineeringUnderstandingReport:
        all_objects = list(graph.nodes)
        all_objects.extend(_diagnostic_nodes(diagnostics))
        all_objects.extend(_document_nodes(documents or []))
        all_objects.extend(_knowledge_nodes(knowledge_documents or []))
        relationships = self.resolver.resolve(
            graph,
            diagnostics=diagnostics,
            documents=documents or [],
            knowledge_documents=knowledge_documents or [],
        )
        connected_ids = {relationship.source_id for relationship in relationships} | {
            relationship.target_id for relationship in relationships
        }
        return EngineeringUnderstandingReport.build(
            object_count=len(all_objects),
            relationships=relationships,
            object_types=_count_by_type(all_objects),
            relationship_types=_count_relationships(relationships),
            orphan_objects=[asdict(node) for node in all_objects if node.id not in connected_ids],
        )


def _diagnostic_nodes(diagnostics: DiagnosticReport | None) -> list[GraphNode]:
    if diagnostics is None:
        return []
    return [
        GraphNode(
            id=f"diagnostic:{issue.id}",
            type=EngineeringObjectType.DIAGNOSTIC,
            name=issue.title,
            source_file=issue.source_file,
            source_line=issue.source_line,
            metadata={
                "rule_id": issue.rule_id,
                "severity": issue.severity,
                "category": issue.category,
                "recommendation": issue.recommendation,
            },
        )
        for issue in diagnostics.issues
    ]


def _document_nodes(documents: list[Document]) -> list[GraphNode]:
    return [
        GraphNode(
            id=document.id,
            type=_document_node_type(document.type),
            name=document.filename,
            source_file=document.filename,
            metadata={
                "mime_type": document.mime_type,
                "size": document.size,
                "modified_at": document.modified_at,
            },
        )
        for document in documents
    ]


def _knowledge_nodes(knowledge_documents: list[dict[str, Any]]) -> list[GraphNode]:
    return [
        GraphNode(
            id=str(item.get("document_id") or f"knowledge:{index}"),
            type=EngineeringObjectType.KNOWLEDGE_REFERENCE,
            name=str(item.get("name") or _safe_file_name(item.get("path")) or "Knowledge Reference"),
            source_file=_safe_file_name(item.get("path")),
            metadata={"source": "knowledge_store"},
        )
        for index, item in enumerate(knowledge_documents)
    ]


def _document_node_type(document_type: str) -> str:
    normalized = document_type.upper()
    if normalized == "PDF":
        return EngineeringObjectType.MANUAL
    if normalized in {"XLSX", "CSV"}:
        return EngineeringObjectType.SPECIFICATION
    return EngineeringObjectType.DOCUMENT


def _count_by_type(nodes: list[GraphNode]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes:
        counts[node.type] = counts.get(node.type, 0) + 1
    return counts


def _safe_file_name(path_or_name: Any) -> str | None:
    if not path_or_name:
        return None
    return Path(str(path_or_name)).name


def _count_relationships(relationships) -> dict[str, int]:
    counts: dict[str, int] = {}
    for relationship in relationships:
        counts[relationship.type] = counts.get(relationship.type, 0) + 1
    return counts
