from __future__ import annotations

from pathlib import Path

from app.tools.files.content_extractors import extract_text, extract_text_from_pdf, extract_text_from_text_file
from hammer_jarvis.documents.models import Document, DocumentContent


class PDFExtractor:
    def extract(self, document: Document) -> DocumentContent:
        result = extract_text_from_pdf(Path(document.path))
        warnings: list[str] = []
        reason = result.get("reason")
        if reason == "ocr_required":
            warnings.append("OCR_REQUIRED")
            warnings.append("OCR_NOT_AVAILABLE")
        elif result.get("error") or result.get("success") is False:
            warnings.append(str(reason or "EXTRACTION_FAILED").upper())

        text = str(result.get("text") or "")
        return DocumentContent(
            text=text,
            page_count=int(result.get("page_count") or 0),
            has_text_layer=bool(text.strip()),
            extracted_with="PDFExtractor",
            warnings=warnings,
        )


class TextExtractor:
    def extract(self, document: Document) -> DocumentContent:
        text = extract_text_from_text_file(Path(document.path))
        return DocumentContent(
            text=text,
            page_count=0,
            has_text_layer=bool(text.strip()),
            extracted_with="TextExtractor",
        )


class CSVExtractor:
    def extract(self, document: Document) -> DocumentContent:
        result = extract_text(Path(document.path))
        warnings: list[str] = []
        if result.get("error") or result.get("success") is False:
            warnings.append(str(result.get("reason") or "EXTRACTION_FAILED").upper())
        text = str(result.get("text") or "")
        return DocumentContent(
            text=text,
            page_count=0,
            has_text_layer=bool(text.strip()),
            extracted_with="CSVExtractor",
            warnings=warnings,
        )


def extract_document(document: Document) -> DocumentContent:
    if document.type == "PDF":
        return PDFExtractor().extract(document)
    if document.type == "CSV":
        return CSVExtractor().extract(document)
    if document.type in {"TXT", "XML"}:
        return TextExtractor().extract(document)
    return DocumentContent(
        text="",
        page_count=0,
        has_text_layer=False,
        extracted_with="UnsupportedExtractor",
        warnings=[f"UNSUPPORTED_DOCUMENT_TYPE:{document.type}"],
    )
