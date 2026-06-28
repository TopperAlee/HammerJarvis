import re
from typing import Any

from hammer_jarvis.tools.protool.panels import get_panel_spec


PLACEHOLDER_PATTERN = re.compile(r"<#+>|%0?\d*[ds]|{[0-9]+}")
METADATA_PREFIXES = ("$_", "#", "$", "@")
LANGUAGE_HEADER_PATTERN = re.compile(r"^\d+\(\d+\)\s+\w+(?:\s+\w+)*$", re.IGNORECASE)
LANGUAGE_HEADER_WORDS = ("polish", "german")


def validate_rows(
    rows: list[list[str]],
    panel: str,
    text_column: int,
    encoding: str = "cp1252",
    report_empty_texts: bool = False,
) -> list[dict[str, Any]]:
    spec = get_panel_spec(panel)
    _validate_text_column(rows, text_column)

    column_index = text_column - 1
    issues: list[dict[str, Any]] = []

    for row_number, row in enumerate(rows, start=1):
        text = row[column_index] if column_index < len(row) else ""
        if should_ignore_text(text, report_empty_texts=report_empty_texts):
            continue
        if report_empty_texts and text == "":
            issues.append({"row": row_number, "type": "EMPTY_TEXT", "text": text})

        text_lines = text.splitlines() or [text]
        if len(text_lines) > spec.rows:
            issues.append(
                {
                    "row": row_number,
                    "type": "TOO_MANY_LINES",
                    "max": spec.rows,
                    "actual": len(text_lines),
                    "text": text,
                }
            )

        for line_number, line in enumerate(text_lines, start=1):
            line_length = len(line)
            if line_length > spec.columns:
                issues.append(
                    {
                        "row": row_number,
                        "type": "TEXT_TOO_LONG",
                        "line": line_number,
                        "max": spec.columns,
                        "actual": line_length,
                        "text": line,
                    }
                )

        try:
            text.encode(encoding)
        except UnicodeEncodeError:
            issues.append(
                {
                    "row": row_number,
                    "type": "ENCODING_ERROR",
                    "encoding": encoding,
                    "text": text,
                }
            )
        except LookupError as exc:
            raise ValueError(f"Unsupported encoding: {encoding}") from exc

    issues.extend(validate_placeholder_consistency(rows, text_column, report_empty_texts=report_empty_texts))

    return issues


def extract_placeholders(text: str) -> list[str]:
    return [match.group(0) for match in PLACEHOLDER_PATTERN.finditer(text)]


def collect_placeholders(
    rows: list[list[str]],
    text_column: int,
    report_empty_texts: bool = False,
) -> list[dict[str, Any]]:
    _validate_text_column(rows, text_column)
    column_index = text_column - 1
    placeholder_rows: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        if row_number == 1:
            continue
        text = row[column_index] if column_index < len(row) else ""
        if should_ignore_text(text, report_empty_texts=report_empty_texts):
            continue
        placeholders = extract_placeholders(text)
        if placeholders:
            placeholder_rows.append({"row": row_number, "placeholders": placeholders, "text": text})
    return placeholder_rows


def validate_placeholder_consistency(
    rows: list[list[str]],
    text_column: int,
    report_empty_texts: bool = False,
) -> list[dict[str, Any]]:
    _validate_text_column(rows, text_column)
    column_index = text_column - 1
    grouped: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        if row_number == 1:
            continue
        text = row[column_index] if column_index < len(row) else ""
        if should_ignore_text(text, report_empty_texts=report_empty_texts):
            continue
        key = _placeholder_group_key(row, column_index)
        placeholders = extract_placeholders(text)
        if key not in grouped:
            grouped[key] = {"row": row_number, "placeholders": placeholders, "text": text, "seen": 1}
            continue
        grouped[key]["seen"] += 1
        expected = grouped[key]["placeholders"]
        if placeholders != expected:
            issues.append(
                {
                    "row": row_number,
                    "type": "PLACEHOLDER_MISMATCH",
                    "reference_row": grouped[key]["row"],
                    "key": key,
                    "expected": expected,
                    "actual": placeholders,
                    "text": text,
                }
            )
    return issues


def _placeholder_group_key(row: list[str], text_column_index: int) -> str:
    for index, value in enumerate(row):
        if index != text_column_index and value != "":
            return value
    return ""


def count_checked_rows(rows: list[list[str]], text_column: int, report_empty_texts: bool = False) -> int:
    _validate_text_column(rows, text_column)
    column_index = text_column - 1
    return sum(
        1
        for row in rows
        if not should_ignore_text(
            row[column_index] if column_index < len(row) else "",
            report_empty_texts=report_empty_texts,
        )
    )


def should_ignore_text(text: str, report_empty_texts: bool = False) -> bool:
    if text.startswith(METADATA_PREFIXES):
        return True
    if text == "" and not report_empty_texts:
        return True
    normalized = text.strip().lower()
    if any(language in normalized for language in LANGUAGE_HEADER_WORDS):
        return True
    if LANGUAGE_HEADER_PATTERN.match(text.strip()):
        return True
    return False


def _validate_text_column(rows: list[list[str]], text_column: int) -> None:
    if text_column < 1:
        raise ValueError("text_column must be 1-based and greater than 0.")
    max_columns = max((len(row) for row in rows), default=0)
    if max_columns == 0:
        raise ValueError("CSV file contains no columns.")
    if text_column > max_columns:
        raise ValueError(f"text_column {text_column} is outside the CSV column range 1..{max_columns}.")
