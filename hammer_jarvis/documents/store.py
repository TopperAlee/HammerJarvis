from __future__ import annotations

from dataclasses import asdict
from typing import Any

from hammer_jarvis.documents.models import Document, DocumentContent
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphEdge, GraphNode


class DocumentStore:
    """In-memory document registry for read-only document intelligence v1."""

    DOCUMENT_NODE_TYPES = {
        "PDF": "Document",
        "DOCX": "Document",
        "XLSX": "Spreadsheet",
        "PPTX": "Document",
        "PNG": "Image",
        "JPG": "Image",
        "CSV": "Spreadsheet",
        "TXT": "Document",
        "XML": "Specification",
    }

    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}
        self._contents: dict[str, DocumentContent] = {}
        self._knowledge_registry: dict[str, dict[str, Any]] = {}

    def save(self, document: Document, content: DocumentContent) -> None:
        self._documents[document.id] = document
        self._contents[document.id] = content

    def get(self, document_id: str) -> Document | None:
        return self._documents.get(document_id)

    def get_content(self, document_id: str) -> DocumentContent | None:
        return self._contents.get(document_id)

    def list(self) -> list[Document]:
        return list(self._documents.values())

    def attach_to_graph(
        self,
        graph: EngineeringGraph,
        document: Document,
        project_file_id: str | None = None,
    ) -> GraphNode:
        node_type = self.DOCUMENT_NODE_TYPES.get(document.type, "Document")
        existing = graph.get_node(document.id)
        if existing:
            return existing
        node = GraphNode(
            id=document.id,
            type=node_type,
            name=document.filename,
            source_file=document.path,
            metadata={
                "document_type": document.type,
                "mime_type": document.mime_type,
                "size": document.size,
            },
        )
        graph.nodes.append(node)
        if project_file_id:
            graph.edges.append(
                GraphEdge(
                    source_id=project_file_id,
                    target_id=document.id,
                    type="CONTAINS",
                    metadata={"source": "document_intelligence"},
                )
            )
        return node

    def register_for_knowledge(self, document: Document) -> dict[str, Any]:
        registration = {
            "registered": True,
            "auto_indexed": False,
            "document_id": document.id,
            "filename": document.filename,
            "type": document.type,
        }
        self._knowledge_registry[document.id] = registration
        return registration

    def document_payload(self, document_id: str) -> dict[str, Any] | None:
        document = self.get(document_id)
        return asdict(document) if document else None

    def content_payload(self, document_id: str) -> dict[str, Any] | None:
        content = self.get_content(document_id)
        return asdict(content) if content else None
