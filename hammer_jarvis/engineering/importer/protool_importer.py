from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from hammer_jarvis.engineering.graph import EngineeringGraph, GraphEdge, GraphNode
from hammer_jarvis.engineering.models import ProjectFile
from hammer_jarvis.tools.protool.report import analyze_protool_csv


class ProToolImporter:
    """Read-only importer that turns ProTool CSV text rows into graph objects."""

    def import_project_file(
        self,
        project_file: ProjectFile,
        *,
        panel: str,
        text_column: int,
        encoding: str = "cp1252",
        project_file_node_id: str | None = None,
    ) -> dict[str, Any]:
        if not project_file.path:
            raise ValueError("ProjectFile path is required for ProTool import.")
        return self.import_file(
            project_file.path,
            panel=panel,
            text_column=text_column,
            encoding=encoding,
            project_file_node_id=project_file_node_id,
            project_file_metadata={"project_file": asdict(project_file)},
        )

    def import_file(
        self,
        file_path: str | Path,
        *,
        panel: str,
        text_column: int,
        encoding: str = "cp1252",
        project_file_node_id: str | None = None,
        project_file_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = Path(file_path)
        report = analyze_protool_csv(
            path,
            panel=panel,
            text_column=text_column,
            encoding=encoding,
            include_preview=True,
        )
        file_node_id = project_file_node_id or _project_file_node_id(path)
        file_node = GraphNode(
            id=file_node_id,
            type="ProjectFile",
            name=path.name,
            source_file=str(path),
            metadata={
                "module": "protool",
                "kind": "protool_csv",
                "encoding": report.get("encoding"),
                "delimiter": report.get("delimiter"),
                "text_column": text_column,
                **(project_file_metadata or {}),
            },
        )
        issue_rows = _issues_by_row(report.get("issues") or [])
        text_nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        for preview_row in report.get("preview_rows") or []:
            row_number = int(preview_row.get("row") or 0)
            text_value = str(preview_row.get("text") or "")
            node = GraphNode(
                id=_text_resource_node_id(path, row_number, panel, text_value),
                type="TextResource",
                name=_text_name(text_value, row_number),
                source_file=str(path),
                source_line=row_number,
                metadata={
                    "text": text_value,
                    "row": row_number,
                    "panel": panel,
                    "language": None,
                    "preview": preview_row.get("preview") or [],
                    "truncated": bool(preview_row.get("truncated")),
                    "placeholders": preview_row.get("placeholders") or [],
                    "issues": issue_rows.get(row_number, []),
                    "encoding": report.get("encoding"),
                    "delimiter": report.get("delimiter"),
                    "text_column": text_column,
                },
            )
            text_nodes.append(node)
            edges.append(
                GraphEdge(
                    source_id=file_node.id,
                    target_id=node.id,
                    type="DEFINES",
                    metadata={"source": "protool_importer", "row": row_number},
                )
            )

        graph = EngineeringGraph(nodes=[file_node, *text_nodes], edges=edges)
        return {
            "file": str(file_path),
            "panel": panel,
            "text_resource_count": len(text_nodes),
            "graph": graph,
            "text_resources": text_nodes,
            "report": report,
        }


def _project_file_node_id(path: Path) -> str:
    return f"file:protool:{_stable_hash(str(path.resolve()).lower())}"


def _text_resource_node_id(path: Path, row: int, panel: str, text: str) -> str:
    source = f"{path.resolve()}|{row}|{panel}|{text}"
    return f"text:protool:{_stable_hash(source)}"


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _text_name(text: str, row: int) -> str:
    compact = " ".join(text.split())
    return compact[:64] if compact else f"TextResource Zeile {row}"


def _issues_by_row(issues: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for issue in issues:
        try:
            row = int(issue.get("row"))
        except (TypeError, ValueError):
            continue
        grouped.setdefault(row, []).append(issue)
    return grouped
