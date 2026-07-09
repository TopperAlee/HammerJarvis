from __future__ import annotations

from hammer_jarvis.research.models import ResearchRequest, ResearchSource


class ContextBuilder:
    def build_prompt(self, request: ResearchRequest, sources: list[ResearchSource]) -> str:
        sections = [
            "System",
            "Du bist Hammer Jarvis. Nutze ausschliesslich den folgenden lokalen Research-Kontext.",
            "",
            "Aktueller Kontext",
            _format_context(request),
            "",
            "Engineering Graph Treffer",
            _format_sources(sources, "GRAPH"),
            "",
            "Knowledge Treffer",
            _format_sources(sources, "KNOWLEDGE"),
            "",
            "Dokumente",
            _format_sources(sources, "DOCUMENT"),
            "",
            "Capabilities",
            _format_sources(sources, "CAPABILITY"),
            "",
            "Benutzerfrage",
            request.query.strip(),
        ]
        return "\n".join(sections).strip()


def _format_context(request: ResearchRequest) -> str:
    rows = {
        "active_project": request.active_project,
        "active_file": request.active_file,
        "active_panel": request.active_panel,
        **request.active_context,
    }
    visible = [f"- {key}: {value}" for key, value in rows.items() if value not in (None, "", [], {})]
    return "\n".join(visible) if visible else "- Kein aktiver Kontext."


def _format_sources(sources: list[ResearchSource], source_type: str) -> str:
    relevant = [source for source in sources if source.type == source_type]
    if not relevant:
        return "- Keine lokalen Treffer."
    return "\n".join(f"- {source.title}: {source.summary}" for source in relevant)
