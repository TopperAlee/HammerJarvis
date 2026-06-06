import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError


SUPPORTED_CONTENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm", ".csv", ".txt", ".md", ".json"}
TEXT_PREVIEW_CHARS = 1000


def extract_text_from_pdf(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size == 0:
            return _pdf_error("empty_or_placeholder_file", "Datei ist leer oder ein Platzhalter.")
        with path.open("rb") as file:
            header = file.read(4)
        if header != b"%PDF":
            return _pdf_error("invalid_pdf_header", "Datei hat keine gültige PDF-Signatur.")
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return {"success": True, "text": text, "error": False}
    except (PdfReadError, PdfStreamError, EOFError, ValueError):
        return _pdf_error("pdf_parse_error", "PDF konnte nicht gelesen werden.")
    except Exception:
        return _pdf_error("pdf_parse_error", "PDF konnte nicht gelesen werden.")


def extract_text_from_docx(path: Path) -> str:
    document = Document(path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def extract_text_from_xlsx(path: Path) -> str:
    workbook = load_workbook(path, read_only=True, data_only=True)
    values: list[str] = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            values.extend(str(value) for value in row if value is not None)
    workbook.close()
    return "\n".join(values)


def extract_text_from_text_file(path: Path) -> str:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as file:
            return "\n".join(" ".join(row) for row in csv.reader(file))
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8", errors="ignore") as file:
            return json.dumps(json.load(file), ensure_ascii=False)
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_text(path: Path) -> dict[str, Any]:
    try:
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_CONTENT_EXTENSIONS:
            return {"path": str(path), "supported": False, "skipped": True, "reason": "nicht unterstuetzter Dateityp"}
        max_bytes = int(float(os.getenv("FILE_CONTENT_MAX_FILE_SIZE_MB", "25")) * 1024 * 1024)
        if path.stat().st_size > max_bytes:
            return {"path": str(path), "supported": True, "skipped": True, "reason": "Datei zu gross"}
        if suffix == ".pdf":
            pdf_result = extract_text_from_pdf(path)
            if not pdf_result.get("success"):
                return {
                    "path": str(path),
                    "success": False,
                    "supported": True,
                    "skipped": True,
                    "error": True,
                    "reason": pdf_result.get("reason"),
                    "message": pdf_result.get("message"),
                    "text": "",
                }
            text = str(pdf_result.get("text", ""))
        elif suffix == ".docx":
            text = extract_text_from_docx(path)
        elif suffix in {".xlsx", ".xlsm"}:
            text = extract_text_from_xlsx(path)
        else:
            text = extract_text_from_text_file(path)
        text = clean_extracted_text(text)
        return {
            "path": str(path),
            "supported": True,
            "skipped": False,
            "text": text,
            "preview": text[:TEXT_PREVIEW_CHARS],
        }
    except Exception as exc:
        return {"path": str(path), "supported": True, "skipped": False, "error": True, "message": str(exc), "text": ""}


def _pdf_error(reason: str, message: str) -> dict[str, Any]:
    return {"success": False, "text": "", "error": True, "reason": reason, "message": message}


def clean_extracted_text(text: str) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
    cleaned = re.sub(r"(\w)-\s+(\w)", r"\1\2", cleaned)
    cleaned = re.sub(r"([a-zäöüß])([A-ZÄÖÜ])", r"\1 \2", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:TEXT_PREVIEW_CHARS * 20]
