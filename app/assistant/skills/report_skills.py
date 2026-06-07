from typing import Any

from app.agent.permissions import ActionRisk
from app.assistant.tool_registry import ToolRegistry
from app.tools.files.path_safety import sanitize_filename


class FileSearchReportSkill:
    """Create a local Markdown report from safe file or content search results."""

    name = "file_search_report"
    description = "Erstellt einen Markdown-Suchbericht aus lokalen Dateitreffern."
    risk = ActionRisk.GREEN
    required_tools = ["file_search", "file_content_search", "file_create_markdown"]

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Search allowed directories and write a Markdown report to exports."""
        query = str(input_data.get("query") or "").strip()
        extensions = input_data.get("extensions")
        content_search = bool(input_data.get("content_search"))
        search_tool = "file_content_search" if content_search else "file_search"
        search_result = _tool_result(
            self.tool_registry.execute_tool(search_tool, {"query": query, "extensions": extensions})
        )
        markdown = _file_report_markdown(query, search_result, content_search)
        created = _tool_result(
            self.tool_registry.execute_tool(
                "file_create_markdown",
                {
                    "title": f"Suchbericht {query or 'Dateien'}",
                    "content": markdown,
                    "filename": f"suchbericht_{sanitize_filename(query or 'dateien')}.md",
                },
            )
        )
        return {"skill": self.name, "risk": self.risk, "search": search_result, **created}


class DocumentIndexExcelSkill:
    """Create a local Excel index from safe file search results."""

    name = "document_index_excel"
    description = "Erstellt eine Excel-Übersicht gefundener Dokumente."
    risk = ActionRisk.GREEN
    required_tools = ["file_search", "file_create_excel"]

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Search files and export a structured index workbook."""
        query = str(input_data.get("query") or "").strip()
        extensions = input_data.get("extensions")
        search_result = _tool_result(
            self.tool_registry.execute_tool("file_search", {"query": query, "extensions": extensions})
        )
        rows = [
            [
                file.get("name", ""),
                file.get("path", ""),
                file.get("extension", ""),
                file.get("size_bytes", ""),
                file.get("modified_at", ""),
                ", ".join(file.get("match_sources", [])),
                file.get("score", ""),
                _short_note(file),
            ]
            for file in search_result.get("files", [])
        ]
        created = _tool_result(
            self.tool_registry.execute_tool(
                "file_create_excel",
                {
                    "title": f"Dokumentenindex {query or 'Dateien'}",
                    "filename": f"dokumentenindex_{sanitize_filename(query or 'dateien')}.xlsx",
                    "sheets": [
                        {
                            "name": "Dokumentenindex",
                            "headers": [
                                "Dateiname",
                                "Pfad",
                                "Typ",
                                "Größe",
                                "Geändert am",
                                "Trefferart",
                                "Score",
                                "Kurznotiz",
                            ],
                            "rows": rows,
                        }
                    ],
                },
            )
        )
        return {"skill": self.name, "risk": self.risk, "search": search_result, **created}


class WebResearchReportSkill:
    """Create a source-based Markdown report from configured web research."""

    name = "web_research_report"
    description = "Erstellt einen Markdown-Bericht aus Webrecherche-Quellen."
    risk = ActionRisk.GREEN
    required_tools = ["web_research", "file_create_markdown"]

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Research through the configured provider and write only returned sources."""
        query = str(input_data.get("query") or "").strip()
        research = _tool_result(self.tool_registry.execute_tool("web_research", {"query": query}))
        markdown = _web_report_markdown(query, research)
        created = _tool_result(
            self.tool_registry.execute_tool(
                "file_create_markdown",
                {
                    "title": f"Webbericht {query or 'Recherche'}",
                    "content": markdown,
                    "filename": f"webbericht_{sanitize_filename(query or 'recherche')}.md",
                },
            )
        )
        return {"skill": self.name, "risk": self.risk, "research": research, **created}


class WebResearchExcelSkill:
    """Create a local Excel source list from configured web research."""

    name = "web_research_excel"
    description = "Erstellt eine Excel-Quellenliste aus Webrecherche."
    risk = ActionRisk.GREEN
    required_tools = ["web_research", "file_create_excel"]

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Research and export source metadata without inventing URLs."""
        query = str(input_data.get("query") or "").strip()
        research = _tool_result(self.tool_registry.execute_tool("web_research", {"query": query}))
        confidence = research.get("confidence", "")
        rows = [
            [
                source.get("title", ""),
                source.get("url", ""),
                source.get("domain", ""),
                source.get("source_quality", ""),
                source.get("snippet", ""),
                source.get("relevance_reason", ""),
                confidence,
            ]
            for source in research.get("sources", [])
        ]
        created = _tool_result(
            self.tool_registry.execute_tool(
                "file_create_excel",
                {
                    "title": f"Webquellen {query or 'Recherche'}",
                    "filename": f"webquellen_{sanitize_filename(query or 'recherche')}.xlsx",
                    "sheets": [
                        {
                            "name": "Quellen",
                            "headers": [
                                "Titel",
                                "URL",
                                "Domain",
                                "Quellenqualität",
                                "Kurzinhalt",
                                "Relevanz",
                                "Vertrauensniveau",
                            ],
                            "rows": rows,
                        }
                    ],
                },
            )
        )
        return {"skill": self.name, "risk": self.risk, "research": research, **created}


def _tool_result(executed: dict[str, Any]) -> dict[str, Any]:
    return executed.get("result", executed)


def _file_report_markdown(query: str, result: dict[str, Any], content_search: bool) -> str:
    lines = [
        f"## Suchanfrage",
        query or "-",
        "",
        f"## Suchmodus",
        "Dateiinhalt" if content_search else "Dateiname/Pfad",
        "",
        "## Durchsuchte Ordner",
    ]
    lines.extend(f"- {directory}" for directory in result.get("searched_dirs", []))
    lines.extend(["", f"## Ergebnisanzahl", str(result.get("count", 0)), "", "## Top-Dateien"])
    for index, file in enumerate(result.get("files", [])[:25], start=1):
        lines.append(f"{index}. {file.get('name', '')}")
        lines.append(f"   - Pfad: {file.get('path', '')}")
        lines.append(f"   - Trefferart: {', '.join(file.get('match_sources', []))}")
        if file.get("snippets"):
            lines.append(f"   - Snippet: {file['snippets'][0]}")
    lines.extend(["", "## Einschränkungen", "- Es wurden nur konfigurierte erlaubte Ordner durchsucht."])
    return "\n".join(lines)


def _web_report_markdown(query: str, research: dict[str, Any]) -> str:
    lines = [
        "## Recherchefrage",
        query or str(research.get("query") or "-"),
        "",
        "## Kurzantwort",
        str(research.get("summary") or research.get("message") or ""),
        "",
        "## Quellen",
    ]
    for index, source in enumerate(research.get("sources", []), start=1):
        lines.append(f"{index}. {source.get('title', 'Quelle')}")
        lines.append(f"   - URL: {source.get('url', '')}")
        lines.append(f"   - Qualität: {source.get('source_quality', '')}")
    lines.extend(
        [
            "",
            "## Einordnung",
            f"- Vertrauen: {research.get('confidence', 'niedrig')}",
            f"- Einschränkungen: {research.get('limitations', '')}",
        ]
    )
    return "\n".join(lines)


def _short_note(file: dict[str, Any]) -> str:
    snippets = file.get("snippets") or []
    if snippets:
        return str(snippets[0])[:180]
    if file.get("path_match_only"):
        return "Nur Pfadtreffer"
    return ""
