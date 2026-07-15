# Document Intelligence Foundation

## Ziel

Document Intelligence erweitert Hammer Jarvis um eine lokale, read-only Dokumentebene. Dokumente werden klassifiziert, Metadaten werden registriert und vorhandene Textlayer werden extrahiert, ohne Quelldateien zu verändern.

Der erste Stand ist eine Foundation. Er bereitet spätere Dokumentanalyse, Engineering-Graph-Verknüpfung, lokale OCR und Knowledge-Workflows vor, führt aber noch keine LLM-Auswertung und keine automatische Indizierung aus.

## Architektur

```text
Lokale Datei
  |
  v
DocumentClassifier
  |
  v
Document Model
  |
  v
Extractor Adapter
  |
  v
DocumentStore
  |
  +--> Engineering Graph Node
  +--> Knowledge registration metadata
```

## Dokumentmodell

`Document` enthält stabile Metadaten:

- id
- filename
- path
- type
- mime_type
- size
- created_at
- modified_at
- metadata

`DocumentContent` enthält das read-only Extraktionsergebnis:

- text
- page_count
- has_text_layer
- extracted_with
- language
- warnings

## Klassifikation

Die Klassifikation erfolgt ausschließlich anhand von Dateiendung und MIME-Type. Es werden keine Dokumentinhalte geöffnet, um den Typ zu bestimmen.

Unterstützte Typen:

- PDF
- DOCX
- XLSX
- PPTX
- PNG
- JPG
- CSV
- TXT
- XML

## Extraktionspipeline

Die erste Pipeline implementiert Adapter für:

- PDF
- CSV
- TXT/XML

PDFs werden auf vorhandene Textlayer geprüft. Wenn ein gültiges PDF keinen extrahierbaren Text enthält, wird `OCR_REQUIRED` gesetzt. Es wird kein OCR ausgeführt.

CSV und TXT werden lokal gelesen. Fehler werden strukturiert als Warnungen zurückgegeben und dürfen den Prozess nicht abbrechen.

## OCR Adapter

OCR ist als Interface vorgesehen:

- `DocumentOCR.supports(document)`
- `DocumentOCR.extract(document)`

Der aktuelle Adapter `NullOCR` gibt immer `OCR_NOT_AVAILABLE` zurück. Spätere lokale Adapter können ergänzen:

- Tesseract
- PaddleOCR
- Windows OCR

Cloud-OCR ist kein Bestandteil dieses Designs.

## Engineering Graph Integration

Dokumente können als Nodes in den Engineering Graph aufgenommen werden:

- PDF/DOCX/TXT/PPTX: `Document`
- XLSX/CSV: `Spreadsheet`
- PNG/JPG: `Image`
- XML: `Specification`

Die Zielbeziehung ist:

```text
Project
  -> ProjectFile
     -> Document
```

Die Foundation stellt dafür nur das Datenmodell und die Store-Hilfsfunktion bereit. Parser und tiefere fachliche Zuordnungen folgen später.

## Knowledge Integration

Dokumente können für Knowledge registriert werden. In v0.9.1 bedeutet das nur:

- Dokument-ID merken
- Typ und Dateiname speichern
- `auto_indexed=false`

Es findet keine automatische Indizierung statt.

## API

Read-only Endpoints:

- `POST /assistant/documents/open`
- `GET /assistant/documents/{id}`
- `GET /assistant/documents/{id}/content`
- `GET /assistant/documents/types`
- `GET /assistant/documents/status/{id}`

## Sicherheitsmodell

- Dokumente werden nicht verändert.
- Es gibt keinen Schreibpfad zurück in Quelldateien.
- Es wird keine Cloud-OCR verwendet.
- Es werden keine Dokumentinhalte geloggt.
- Es findet keine LLM-Auswertung statt.
- OCR ist nur als lokaler Adapter vorgesehen.

## Erweiterungspunkte

- DOCX/XLSX/PPTX-spezifische Extraktoren
- lokale OCR Adapter
- Dokument-zu-Engineering-Objekt-Zuordnung
- automatische, explizit gestartete Knowledge-Indizierung
- Dokumentdiagnosen im Diagnostics Engine Kontext
