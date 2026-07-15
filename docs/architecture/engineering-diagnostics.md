# Engineering Diagnostics Engine

## Ziel

Die Engineering Diagnostics Engine führt deterministische, read-only Prüfungen
auf Engineering-Objekten aus. Sie nutzt den Engineering Object Graph,
ProTool-Importdaten und Projektmetadaten, verändert aber keine Projektdateien.

## Regelmodell

Eine Diagnose-Regel ist einzeln registrierbar und besitzt:

- `rule_id`
- `name`
- `category`
- `description`
- `default_severity`
- `applicable_node_types`
- `enabled`

Regeln liefern `DiagnosticIssue`-Objekte. Jede Regel ist deterministisch und
muss ohne LLM, Websuche oder externe APIs funktionieren.

## Explainability

Jedes Issue enthält:

- auslösende Regel
- betroffenen Knoten oder Datei
- konkrete Evidence
- Empfehlung
- Severity
- Kategorie

Eine Diagnose darf keine unbegründete Behauptung sein. Technische
Regelfehler werden nur als Statistik im Report dokumentiert.

## Sicherheitsprinzip

Die Engine ist read-only:

- keine Projektdateien ändern
- keine CSV schreiben
- keine Übersetzung
- keine Exporte überschreiben
- keine PLC- oder HMI-Schreibaktionen

## API

Read-only Endpoints:

```text
POST /assistant/engineering/diagnostics/run
GET  /assistant/engineering/diagnostics/latest
GET  /assistant/engineering/diagnostics/rules
GET  /assistant/engineering/diagnostics/issues/{issue_id}
```

Der Run-Endpoint akzeptiert Projekt-ID, Kategorien und minimale Severity.

## Erweiterung

Neue Regeln werden über die `DiagnosticRuleRegistry` registriert. Die
Regellogik liegt in separaten Modulen:

- `text_rules.py`
- `graph_rules.py`
- `project_rules.py`

## Grenzen von v1

- keine LLM-basierten Diagnosen
- keine Websuche
- kein Persistenzspeicher außer letztem In-Memory-Report
- keine automatische Korrektur
- keine Siemens-Projektdateien direkt verändern
