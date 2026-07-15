import io
from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.main import app
from hammer_jarvis.documents.classifier import DocumentClassifier
from hammer_jarvis.documents.extractor import CSVExtractor, PDFExtractor, TextExtractor
from hammer_jarvis.documents.models import Document, DocumentContent
from hammer_jarvis.documents.ocr import NullOCR
from hammer_jarvis.documents.store import DocumentStore
from hammer_jarvis.engineering.graph import EngineeringGraph, GraphNode


client = TestClient(app)


def _blank_pdf(path: Path) -> None:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    path.write_bytes(output.getvalue())


def test_document_models_are_json_compatible(tmp_path: Path) -> None:
    path = tmp_path / "manual.txt"
    path.write_text("Inhalt", encoding="utf-8")
    document = Document.from_path(path, document_type="TXT", mime_type="text/plain")
    content = DocumentContent(text="Inhalt", page_count=0, has_text_layer=True, extracted_with="TextExtractor")

    assert asdict(document)["filename"] == "manual.txt"
    assert asdict(content)["warnings"] == []


def test_document_classifier_detects_supported_types() -> None:
    classifier = DocumentClassifier()

    assert classifier.classify("manual.pdf", "application/pdf") == "PDF"
    assert classifier.classify("anlage.docx", None) == "DOCX"
    assert classifier.classify("tabelle.xlsx", None) == "XLSX"
    assert classifier.classify("folie.pptx", None) == "PPTX"
    assert classifier.classify("bild.png", None) == "PNG"
    assert classifier.classify("bild.jpg", "image/jpeg") == "JPG"
    assert classifier.classify("daten.csv", "text/csv") == "CSV"
    assert classifier.classify("readme.txt", "text/plain") == "TXT"
    assert classifier.classify("export.xml", "application/xml") == "XML"


def test_pdf_extractor_detects_text_layer(monkeypatch, tmp_path: Path) -> None:
    pdf = tmp_path / "manual.pdf"
    pdf.write_bytes(b"%PDF fake")

    class FakePage:
        def extract_text(self):
            return "Hydraulikpumpe pruefen"

    class FakeReader:
        pages = [FakePage()]

        def __init__(self, _path):
            pass

    monkeypatch.setattr("app.tools.files.content_extractors.PdfReader", FakeReader)

    document = Document.from_path(pdf, document_type="PDF", mime_type="application/pdf")
    content = PDFExtractor().extract(document)

    assert content.has_text_layer is True
    assert content.page_count == 1
    assert "Hydraulikpumpe" in content.text
    assert content.extracted_with == "PDFExtractor"


def test_pdf_extractor_marks_blank_pdf_as_ocr_required(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    _blank_pdf(pdf)

    document = Document.from_path(pdf, document_type="PDF", mime_type="application/pdf")
    content = PDFExtractor().extract(document)

    assert content.has_text_layer is False
    assert content.page_count == 1
    assert "OCR_REQUIRED" in content.warnings


def test_text_and_csv_extractors(tmp_path: Path) -> None:
    text_file = tmp_path / "notiz.txt"
    csv_file = tmp_path / "daten.csv"
    text_file.write_text("Lokaler Text", encoding="utf-8")
    csv_file.write_text("Name;Wert\nPumpe;42\n", encoding="utf-8")

    text_content = TextExtractor().extract(Document.from_path(text_file, document_type="TXT", mime_type="text/plain"))
    csv_content = CSVExtractor().extract(Document.from_path(csv_file, document_type="CSV", mime_type="text/csv"))

    assert text_content.text == "Lokaler Text"
    assert "Pumpe" in csv_content.text
    assert csv_content.extracted_with == "CSVExtractor"


def test_null_ocr_reports_not_available(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    _blank_pdf(pdf)
    document = Document.from_path(pdf, document_type="PDF", mime_type="application/pdf")

    assert NullOCR().supports(document) is False
    content = NullOCR().extract(document)
    assert content.warnings == ["OCR_NOT_AVAILABLE"]


def test_document_store_registers_document_content_graph_and_knowledge(tmp_path: Path) -> None:
    store = DocumentStore()
    path = tmp_path / "manual.txt"
    path.write_text("Hydraulik", encoding="utf-8")
    document = Document.from_path(path, document_type="TXT", mime_type="text/plain")
    content = DocumentContent(text="Hydraulik", page_count=0, has_text_layer=True, extracted_with="TextExtractor")

    store.save(document, content)
    graph = EngineeringGraph(nodes=[GraphNode("project:1", "Project", "Projekt", None)])
    store.attach_to_graph(graph, document, project_file_id="file:1")
    knowledge = store.register_for_knowledge(document)

    assert store.get(document.id) == document
    assert store.get_content(document.id) == content
    assert any(node.type == "Document" for node in graph.nodes)
    assert any(edge.type == "CONTAINS" and edge.target_id == document.id for edge in graph.edges)
    assert knowledge["registered"] is True
    assert knowledge["auto_indexed"] is False


def test_document_api_open_status_content_and_types(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(tmp_path))
    path = tmp_path / "notiz.txt"
    path.write_text("Lokaler Dokumenttext", encoding="utf-8")

    opened = client.post("/assistant/documents/open", json={"path": str(path)})
    assert opened.status_code == 200
    document_id = opened.json()["document"]["id"]

    assert client.get("/assistant/documents/types").status_code == 200
    assert client.get(f"/assistant/documents/{document_id}").status_code == 200
    content = client.get(f"/assistant/documents/{document_id}/content")
    status = client.get(f"/assistant/documents/status/{document_id}")
    assert content.status_code == 200
    assert content.json()["text"] == "Lokaler Dokumenttext"
    assert status.status_code == 200
    assert status.json()["extraction_status"] == "extracted"


def test_document_api_rejects_path_outside_allowed_dirs(monkeypatch, tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("nicht lesen", encoding="utf-8")
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(allowed))

    response = client.post("/assistant/documents/open", json={"path": str(secret)})

    assert response.status_code == 400


def test_document_api_unknown_ids_return_404() -> None:
    assert client.get("/assistant/documents/document:missing").status_code == 404
    assert client.get("/assistant/documents/document:missing/content").status_code == 404
    assert client.get("/assistant/documents/status/document:missing").status_code == 404


def test_document_api_invalid_pdf_signature_reports_warning(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FILE_SEARCH_ALLOWED_DIRS", str(tmp_path))
    pdf = tmp_path / "kaputt.pdf"
    pdf.write_bytes(b"not a pdf")

    opened = client.post("/assistant/documents/open", json={"path": str(pdf)})

    assert opened.status_code == 200
    assert "INVALID_PDF_HEADER" in opened.json()["content"]["warnings"]


def test_dashboard_contains_document_intelligence_card() -> None:
    html = Path("app/static/dashboard.html").read_text(encoding="utf-8")
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'id="documentIntelligence"' in html
    assert 'id="documentOpenButton"' in html
    assert 'id="documentOcrStatus"' in html
    assert "OCR erforderlich" in html
    assert "/assistant/documents/open" in js
    assert "openDocumentIntelligence" in js
