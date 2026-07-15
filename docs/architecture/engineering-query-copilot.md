# Engineering Query Copilot

## Ziel

Milestone `v1.0.0-alpha.2` ergaenzt eine read-only Engineering Query Schicht. Sie beantwortet Fragen zum lokalen Engineering-Modell deterministisch aus vorhandenen Daten und formuliert optional eine lesbare Copilot-Antwort.

## Regelbasierter Query Parser

Der Parser in `hammer_jarvis/query/parser.py` nutzt feste Regeln und keine LLM-Auswertung. Er erkennt Objekt-Suche, Beziehungen, Usage, Diagnosen, Dokumente, Waisenobjekte, Relationship-Erklaerungen und Listen nach Objekttyp.

Unbekannte Fragen erzeugen `UNKNOWN` mit einer verstaendlichen Fallback-Antwort statt einer technischen Exception.

## Datenquellen

Die Query Engine liest nur vorhandene In-Memory-Daten:

- Engineering Graph
- Engineering Understanding Report
- Diagnostics Latest Report
- Document Store
- Context Store ueber die API-Integration

Die Engine mutiert keine Engineering-Projektdateien und fuehrt keine Steueraktionen aus.

## Explainability

Jede Beziehung wird aus dem vorhandenen Understanding Relationship Eintrag erklaert. Die Evidence enthaelt vorhandene Edge-Daten, Quell- und Zieltypen sowie die im Understanding Report gespeicherten Evidence-Texte.

Absolute lokale Pfade werden vor API-Ausgabe auf Dateinamen reduziert.

## Copilot-Formulierung

`EngineeringCopilotAnswerBuilder` nimmt ein deterministisches `EngineeringQueryResult` entgegen. Wenn ein ResearchLLM uebergeben wird, darf es nur diese strukturierten Daten formulieren. Ohne LLM wird eine deterministische Fallback-Antwort erzeugt.

Die strukturierten Objekte, Beziehungen, Diagnosen, Dokumente und Evidence bleiben immer Teil der API-Antwort.

## Sicherheitsmodell

Die Capability `engineering.query` ist `GREEN`, `read_only` und fuehrt keine Schreiboperationen auf externen Geraeten oder Projektdateien aus. Empfehlungen werden nur angezeigt und nie automatisch ausgefuehrt.

## API

- `POST /assistant/engineering/query`
- `GET /assistant/engineering/query/latest`
- `GET /assistant/engineering/query/types`
- `GET /assistant/engineering/query/object/{object_id}`
- `GET /assistant/engineering/query/relationship/{relationship_id}/explain`

Fehlerfaelle:

- leere oder ungueltige Query: `400`
- Understanding noch nicht gebaut: `409`
- unbekanntes Objekt oder Beziehung: `404`

## Grenzen von alpha.2

- Der Parser ist absichtlich regelbasiert und erkennt nur die definierten Formulierungen.
- Relationship IDs werden aus Quelle, Typ und Ziel deterministisch abgeleitet.
- Die Copilot-Formulierung nutzt standardmaessig den deterministischen Fallback.
- Dokument-Zuordnung basiert auf vorhandenen Relationships und Store-Metadaten.
