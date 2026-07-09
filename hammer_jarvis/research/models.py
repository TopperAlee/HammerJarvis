from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResearchRequest:
    query: str
    active_context: dict[str, Any] = field(default_factory=dict)
    active_project: str | None = None
    active_file: str | None = None
    active_panel: str | None = None
    include_graph: bool = True
    include_knowledge: bool = True
    include_capabilities: bool = True
    include_documents: bool = True
    include_web: bool = False


@dataclass
class ResearchSource:
    id: str
    type: str
    title: str
    summary: str
    relevance: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchContext:
    request: ResearchRequest
    sources: list[ResearchSource]
    prompt: str
    statistics: dict[str, Any] = field(default_factory=dict)
