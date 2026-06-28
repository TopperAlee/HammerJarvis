from pathlib import Path
from typing import Any

from hammer_jarvis.tools.protool.csv_reader import read_protool_csv
from hammer_jarvis.tools.protool.panels import PanelSpec, get_panel_spec
from hammer_jarvis.tools.protool.validator import (
    collect_placeholders,
    count_checked_rows,
    extract_placeholders,
    should_ignore_text,
    validate_rows,
)


def analyze_protool_csv(
    file_path: str | Path,
    panel: str,
    text_column: int,
    encoding: str = "cp1252",
    report_empty_texts: bool = False,
    include_preview: bool = False,
) -> dict[str, Any]:
    panel_spec = get_panel_spec(panel)
    csv_data = read_protool_csv(file_path, encoding=encoding)
    rows: list[list[str]] = csv_data["rows"]
    issues = validate_rows(
        rows,
        panel=panel,
        text_column=text_column,
        encoding=encoding,
        report_empty_texts=report_empty_texts,
    )
    placeholders = collect_placeholders(rows, text_column=text_column, report_empty_texts=report_empty_texts)

    report = {
        "file": str(file_path),
        "panel": panel,
        "encoding": csv_data["encoding"],
        "delimiter": csv_data["delimiter"],
        "rows": len(rows),
        "checked_rows": count_checked_rows(rows, text_column=text_column, report_empty_texts=report_empty_texts),
        "placeholder_count": sum(len(item["placeholders"]) for item in placeholders),
        "placeholders": placeholders,
        "issues": issues,
    }
    if include_preview:
        preview_rows = build_panel_previews(
            rows,
            panel_spec=panel_spec,
            text_column=text_column,
            report_empty_texts=report_empty_texts,
        )
        report["previews"] = [
            {key: value for key, value in preview.items() if key != "placeholders"}
            for preview in preview_rows
        ]
        report["preview_rows"] = preview_rows
    return report


def build_panel_previews(
    rows: list[list[str]],
    panel_spec: PanelSpec,
    text_column: int,
    report_empty_texts: bool = False,
) -> list[dict[str, Any]]:
    column_index = text_column - 1
    previews: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        if row_number == 1:
            continue
        text = row[column_index] if column_index < len(row) else ""
        if should_ignore_text(text, report_empty_texts=report_empty_texts):
            continue
        preview, truncated = _preview_lines(text, panel_spec)
        previews.append(
            {
                "row": row_number,
                "text": text,
                "preview": preview,
                "truncated": truncated,
                "placeholders": extract_placeholders(text),
            }
        )
    return previews


def _preview_lines(text: str, panel_spec: PanelSpec) -> tuple[list[str], bool]:
    source_lines = text.splitlines() or [text]
    truncated = len(source_lines) > panel_spec.rows
    preview: list[str] = []
    for line in source_lines[: panel_spec.rows]:
        if len(line) > panel_spec.columns:
            truncated = True
        preview.append(line[: panel_spec.columns].ljust(panel_spec.columns))
    while len(preview) < panel_spec.rows:
        preview.append(" " * panel_spec.columns)
    return preview, truncated
