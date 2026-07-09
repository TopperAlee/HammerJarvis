from __future__ import annotations

from typing import Any

from app.assistant.knowledge.knowledge_store import KnowledgeStore
from hammer_jarvis.engineering.graph import GraphBuilder
from hammer_jarvis.intent.capabilities import CapabilityRegistry
from hammer_jarvis.intent.context import ContextStore
from hammer_jarvis.research.context_builder import ContextBuilder
from hammer_jarvis.research.models import ResearchContext, ResearchRequest, ResearchSource


class ResearchOrchestrator:
    def __init__(
        self,
        *,
        context_store: ContextStore | None = None,
        graph_builder: GraphBuilder | None = None,
        knowledge_store: KnowledgeStore | None = None,
        capability_registry: CapabilityRegistry | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.context_store = context_store or ContextStore()
        self.graph_builder = graph_builder or GraphBuilder()
        self.knowledge_store = knowledge_store or KnowledgeStore()
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.context_builder = context_builder or ContextBuilder()

    def build_context(self, request: ResearchRequest) -> ResearchContext:
        normalized_request = self._with_active_context(request)
        sources: list[ResearchSource] = []
        if normalized_request.include_graph:
            sources.extend(self._graph_sources(normalized_request.query))
        if normalized_request.include_knowledge:
            sources.extend(self._knowledge_sources(normalized_request.query))
        if normalized_request.include_documents:
            sources.extend(self._document_sources())
        if normalized_request.include_capabilities:
            sources.extend(self._capability_sources(normalized_request.query))
        prompt = self.context_builder.build_prompt(normalized_request, sources)
        return ResearchContext(
            request=normalized_request,
            sources=sources,
            prompt=prompt,
            statistics={
                "source_count": len(sources),
                "graph_count": _count_type(sources, "GRAPH"),
                "knowledge_count": _count_type(sources, "KNOWLEDGE"),
                "document_count": _count_type(sources, "DOCUMENT"),
                "capability_count": _count_type(sources, "CAPABILITY"),
                "prompt_char_count": len(prompt),
                "web_enabled": False,
            },
        )

    def _with_active_context(self, request: ResearchRequest) -> ResearchRequest:
        context = self.context_store.get().model_dump()
        active_context = {**context, **request.active_context}
        return ResearchRequest(
            query=request.query,
            active_context=active_context,
            active_project=request.active_project or active_context.get("active_project_name") or active_context.get("active_project_id"),
            active_file=request.active_file or active_context.get("active_file"),
            active_panel=request.active_panel or active_context.get("active_panel"),
            include_graph=request.include_graph,
            include_knowledge=request.include_knowledge,
            include_capabilities=request.include_capabilities,
            include_documents=request.include_documents,
            include_web=False,
        )

    def _graph_sources(self, query: str) -> list[ResearchSource]:
        try:
            graph = self.graph_builder.build_demo_graph("demo-project")
        except Exception:
            return []
        return [
            ResearchSource(
                id=f"graph:{node.id}",
                type="GRAPH",
                title=node.name,
                summary=f"{node.type} aus {node.source_file or 'Engineering Graph'}",
                relevance=0.85,
                metadata={"node_id": node.id, "node_type": node.type, "source_file": node.source_file},
            )
            for node in graph.search(query)[:5]
        ]

    def _knowledge_sources(self, query: str) -> list[ResearchSource]:
        result = self.knowledge_store.search_knowledge(query, limit=5)
        return [
            ResearchSource(
                id=f"knowledge:{item.get('document_id', index)}:{item.get('chunk_id', index)}",
                type="KNOWLEDGE",
                title=str(item.get("document_name") or item.get("name") or "Knowledge Treffer"),
                summary=str(item.get("snippet") or item.get("text") or "")[:300],
                relevance=float(item.get("score") or 0.5),
                metadata=_safe_metadata(item, ["document_id", "chunk_id", "document_name", "score"]),
            )
            for index, item in enumerate(result.get("results", []))
        ]

    def _document_sources(self) -> list[ResearchSource]:
        result = self.knowledge_store.list_documents()
        return [
            ResearchSource(
                id=f"document:{item.get('document_id', index)}",
                type="DOCUMENT",
                title=str(item.get("original_name") or item.get("name") or "Dokument"),
                summary=f"{item.get('chunk_count', 0)} Chunks, Status {item.get('extraction_status', '-')}",
                relevance=0.35,
                metadata=_safe_metadata(item, ["document_id", "extension", "source_type", "chunk_count", "extraction_status"]),
            )
            for index, item in enumerate(result.get("documents", [])[:5])
        ]

    def _capability_sources(self, query: str) -> list[ResearchSource]:
        terms = query.strip().lower().split()
        matches = []
        fallback = []
        for capability in self.capability_registry.list():
            haystack = " ".join(
                [
                    capability.id,
                    capability.name,
                    capability.module,
                    capability.plugin or "",
                    capability.status,
                ]
            ).lower()
            source = ResearchSource(
                id=f"capability:{capability.id}",
                type="CAPABILITY",
                title=capability.name,
                summary=f"{capability.status}, Risiko {capability.risk_level}, read-only={capability.read_only}",
                relevance=0.6,
                metadata=capability.model_dump(),
            )
            if terms and any(term in haystack for term in terms):
                matches.append(source)
            else:
                fallback.append(source)
        return (matches or fallback)[:5]


def _count_type(sources: list[ResearchSource], source_type: str) -> int:
    return sum(1 for source in sources if source.type == source_type)


def _safe_metadata(item: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: item.get(key) for key in keys if key in item}
