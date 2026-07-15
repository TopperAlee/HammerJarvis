# Engineering Understanding Engine

## Ziel

Die Engineering Understanding Engine baut aus bereits vorhandenen lokalen Daten ein nachvollziehbares Engineering-Modell auf. Sie ersetzt den Engineering Object Graph nicht, sondern wertet ihn zusammen mit Diagnostics, Document Intelligence, Knowledge und Research-Kontext aus.

Der erste Stand ist strikt read-only. Es werden keine Projektdateien geoeffnet, veraendert oder geschrieben.

## Objektmodell

Die Engine arbeitet mit vorhandenen `GraphNode`-Objekten und erweitert die Auswertung um zusaetzliche lokale Objektarten:

- `Project`
- `ProjectFile`
- `TextResource`
- `Document`
- `Manual`
- `Specification`
- `Panel`
- `Screen`
- `Alarm`
- `Variable`
- `Translation`
- `Diagnostic`
- `KnowledgeReference`

Diese Typen sind zunaechst Klassifikationen fuer Auswertung, API und Dashboard. Sie erzwingen keine neue Graphdatenbank und ersetzen keine bestehenden Parser.

## Beziehungstypen

Der Resolver erzeugt nur Beziehungen, die aus vorhandenen Daten begruendet werden koennen:

- `CONTAINS`: Projekt enthaelt Datei oder Dokument.
- `DEFINES`: Projektdatei definiert ein Engineering-Objekt.
- `AFFECTS`: Diagnose-Issue betrifft ein Engineering-Objekt.
- `RELATES_TO`: Dokument bezieht sich auf ein Projekt.
- `REFERENCES`: Knowledge-Eintrag referenziert ein Dokument.

Bestehende Graph-Edges werden uebernommen. Zusaetzliche Beziehungen werden nur aus lokalen Stores, Diagnostics-Reports und eindeutigen Metadaten abgeleitet.

## Explainability

Jede erzeugte Beziehung enthaelt ein `evidence`-Feld. Dieses beschreibt, warum die Beziehung existiert, zum Beispiel:

- bestehende Engineering-Graph-Edge
- Diagnostic Issue referenziert `affected_object_id`
- Dokument liegt im selben lokalen Engineering-Kontext
- Knowledge-Dokument und Document-Intelligence-Dokument teilen Pfad oder Dateiname

Beziehungen ohne Evidence sind nicht erlaubt.

## Erweiterbarkeit

Spaetere Versionen koennen weitere lokale Quellen anbinden:

- ProTool Importer
- WinCC flexible Importer
- TIA Project Indexer
- STEP7 Classic Analyse
- lokale Handbuecher
- Knowledge Base
- Research Answers

Die v1-Implementierung bleibt bewusst speicherbasiert und leichtgewichtig. Eine Graphdatenbank ist nicht Teil dieses Meilensteins.

## Sicherheitsmodell

- Read-only by default.
- Keine externen APIs.
- Keine LLM-Heuristiken fuer Beziehungen.
- Keine Veraenderung von Produktions- oder Projektdateien.
- Keine unbegruendeten Beziehungen.

## Implemented v1

Milestone v1.0.0 Part 1 implementiert:

- `RelationshipResolver`
- `EngineeringUnderstandingEngine`
- In-Memory-Report
- API-Endpunkte fuer Build, Report, Beziehungen und Objektauflösung
- Dashboard-Karte mit Statistik
- Kontext-Update `current_task = engineering.understanding`
