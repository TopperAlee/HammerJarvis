from __future__ import annotations

from typing import Protocol

from hammer_jarvis.documents.models import Document, DocumentContent


class DocumentOCR(Protocol):
    def supports(self, document: Document) -> bool:
        ...

    def extract(self, document: Document) -> DocumentContent:
        ...


class NullOCR:
    """Local OCR adapter placeholder. It never calls cloud services."""

    def supports(self, document: Document) -> bool:
        return False

    def extract(self, document: Document) -> DocumentContent:
        return DocumentContent(
            text="",
            page_count=0,
            has_text_layer=False,
            extracted_with="NullOCR",
            warnings=["OCR_NOT_AVAILABLE"],
        )
