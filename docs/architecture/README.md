# HammerJarvis Architecture

HammerJarvis ist ein lokales Windows-first System mit FastAPI Backend, browserbasiertem Dashboard und modularen Tools fuer Smart Home, Knowledge, Productivity und Engineering.

## Zielarchitektur

### FastAPI Backend

Das Backend stellt lokale HTTP-, WebSocket- und API-Endpunkte bereit. Es orchestriert Tools, verwaltet Sicherheitsregeln und kapselt Integrationen wie Home Assistant, Knowledge, Dateien, Web Research und Engineering-Module.

### Dashboard Frontend

Das Dashboard ist ein plain HTML/CSS/JavaScript Frontend ohne Build-System. Es dient als lokale Bedienoberflaeche fuer Chat, Voice, Dateiwerkzeuge, Knowledge, Watcher und Engineering-Assistenten.

### Knowledge Layer

Der Knowledge Layer verwaltet lokale Dokumentaufnahme, Metadaten, Deduplizierung, Extraktion, Suche und kontextbezogene Quellen. Dokumentkontext bleibt getrennt von Memory und wird kontrolliert an den Assistant uebergeben.

### Engineering Plugins

Engineering-Funktionen werden als getrennte Module aufgebaut. Sie sollen read-only starten, klare Reports liefern und spaeter ueber definierte Sicherheitsgrenzen erweitert werden.

### ProTool Assistant

Der ProTool Assistant ist das erste Engineering-Modul. Er analysiert ProTool-CSV-Dateien fuer Panels wie OP7 und TD17, prueft Panelgrenzen, Encoding, Platzhalter und erzeugt eine Vorschau ohne CSV-Dateien zu veraendern.

## Langfristige Plugin-Struktur

Geplante Engineering-Module:

- `protool`: Analyse alter ProTool-Projekte und HMI-Texte.
- `wincc_flexible`: Analyse und QA fuer WinCC-flexible-Projekte.
- `tia`: TIA-Projektindexierung und Strukturverstaendnis.
- `plc`: PLC-Analyse, Querverweise und Symbolauswertung.
- `translator`: HMI-Translation-QA und Terminologiepruefung.
- `diagnostics`: Engineering-Diagnosen, Reports und Projektzustandspruefungen.

## Sicherheitsmodell

Engineering-Module starten read-only. Schreibende Operationen, Projektveraenderungen oder produktionsrelevante Aktionen duerfen erst nach expliziter Sicherheitsentscheidung und bestaetigtem Workflow implementiert werden.

