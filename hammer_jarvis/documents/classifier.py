from __future__ import annotations

from pathlib import Path


class DocumentClassifier:
    """Classifies documents without opening or modifying their contents."""

    EXTENSION_TYPES = {
        ".pdf": "PDF",
        ".docx": "DOCX",
        ".xlsx": "XLSX",
        ".xlsm": "XLSX",
        ".pptx": "PPTX",
        ".png": "PNG",
        ".jpg": "JPG",
        ".jpeg": "JPG",
        ".csv": "CSV",
        ".txt": "TXT",
        ".md": "TXT",
        ".xml": "XML",
    }

    MIME_TYPES = {
        "application/pdf": "PDF",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
        "application/vnd.ms-excel.sheet.macroenabled.12": "XLSX",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PPTX",
        "image/png": "PNG",
        "image/jpeg": "JPG",
        "text/csv": "CSV",
        "text/plain": "TXT",
        "text/markdown": "TXT",
        "application/xml": "XML",
        "text/xml": "XML",
    }

    def classify(self, filename: str, mime_type: str | None = None) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in self.EXTENSION_TYPES:
            return self.EXTENSION_TYPES[suffix]
        if mime_type and mime_type.lower() in self.MIME_TYPES:
            return self.MIME_TYPES[mime_type.lower()]
        return "UNKNOWN"

    def supported_types(self) -> list[dict[str, str]]:
        seen: set[str] = set()
        supported: list[dict[str, str]] = []
        for extension, document_type in self.EXTENSION_TYPES.items():
            key = f"{document_type}:{extension}"
            if key in seen:
                continue
            seen.add(key)
            supported.append({"type": document_type, "extension": extension})
        return supported
