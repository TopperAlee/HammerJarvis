# Engineering Object Graph

## 1. Ziel

HammerJarvis braucht einen gemeinsamen Engineering Object Graph, damit unterschiedliche Engineering-Quellen nicht isoliert als Dateien behandelt werden. ProTool, WinCC flexible, TIA Portal und STEP7 Classic beschreiben oft dieselbe Anlage aus unterschiedlichen Blickwinkeln: HMI-Texte, Alarme, Variablen, Steuerungsbausteine, Dokumentation und Gerätebeziehungen.

Der Engineering Object Graph soll eine gemeinsame Struktur schaffen fuer:

- Suche ueber Projektgrenzen und Dateiformate hinweg.
- Querverweise zwischen HMI, PLC, Dokumentation und Projektdateien.
- Impact-Analyse bei Signalen, Texten, Alarmen und Bausteinen.
- Uebersetzungs- und Placeholder-QA fuer HMI-Texte.
- Reports mit nachvollziehbaren Quellen.
- AI-Abfragen auf Basis strukturierter Engineering-Objekte statt loser Dateisnippets.

## 2. Grundprinzip

Engineering-Daten werden nicht nur als Dateien betrachtet, sondern als Objekte und Beziehungen. Dateien bleiben Quellen, aber die eigentliche Analyse arbeitet auf fachlichen Objekten.

Beispiele fuer Objekte:

- `Project`
- `ProjectFile`
- `TextResource`
- `Alarm`
- `Variable`
- `Screen`
- `Recipe`
- `ProgramBlock`
- `DataBlock`
- `Tag`
- `Connection`
- `Device`
- `Reference`

Ein Parser liest Quelldaten read-only, erzeugt daraus Nodes und Edges und schreibt keine Quelldateien zurueck.

## 3. Node-Typen

Alle Nodes sollen mindestens folgende Pflichtfelder haben:

- `id`: stabile eindeutige ID innerhalb des Graphen.
- `type`: fachlicher Node-Typ.
- `name`: menschenlesbarer Name.
- `source_file`: Quelldatei oder logische Quelle.
- `source_line`: optionale Zeilen- oder Positionsinformation.
- `metadata`: JSON-kompatible Zusatzdaten.

Erste Node-Typen:

### Project

Repraesentiert ein Engineering-Projekt oder einen importierten Projektausschnitt. Metadaten koennen Projektpfad, Modul, Paneltyp oder Importzeitpunkt enthalten.

### ProjectFile

Repraesentiert eine Quelldatei wie `MessageText.csv`, `Variables.csv`, einen TIA-Export oder eine Dokumentationsdatei.

### TextResource

Repraesentiert einen HMI-Text, Meldetext, Hilfetext oder Uebersetzungseintrag. Metadaten koennen Sprache, Placeholder, Panelbreite und Pruefstatus enthalten.

### Alarm

Repraesentiert eine HMI- oder PLC-Meldung. Metadaten koennen Alarmnummer, Klasse, Prioritaet, Trigger-Variable und Quittierverhalten enthalten.

### Variable

Repraesentiert eine technische Variable oder ein Signal. Metadaten koennen Adresse, Datentyp, Symbolik, Kommentar und Quelle enthalten.

### Screen

Repraesentiert ein HMI-Bild oder eine Bedienseite. Metadaten koennen Panel, Screen-ID, Navigation und angezeigte Objekte enthalten.

### Recipe

Repraesentiert ein Rezept oder einen Parametersatz. Metadaten koennen Felder, Datentypen und HMI-Zuordnung enthalten.

### ProgramBlock

Repraesentiert einen PLC-Baustein wie FC, FB, OB oder UDT. Metadaten koennen Bausteinnummer, Sprache, Schnittstelle und Aufrufkontext enthalten.

### DataBlock

Repraesentiert einen PLC-Datenbaustein. Metadaten koennen DB-Nummer, Struktur, Adressen und Symbolik enthalten.

### Device

Repraesentiert ein Panel, eine SPS, einen Antrieb, ein IO-Geraet oder eine Kommunikationskomponente.

### Connection

Repraesentiert eine Kommunikationsverbindung zwischen Geraeten oder Systemteilen. Metadaten koennen Protokoll, Partner, Adresse und Netz enthalten.

### DocumentationReference

Repraesentiert einen Bezug auf Handbuch, Projektnotiz, Knowledge-Dokument oder interne Spezifikation.

## 4. Edge-Typen

Erste Beziehungstypen:

- `CONTAINS`: Projekt oder Datei enthaelt ein Objekt.
- `DEFINES`: Datei oder Block definiert ein Objekt.
- `USES`: Objekt verwendet ein anderes Objekt.
- `WRITES`: Baustein, Screen oder Aktion schreibt eine Variable.
- `READS`: Baustein, Screen oder Diagnose liest eine Variable.
- `DISPLAYS`: Screen, Panel oder Alarm zeigt einen Text an.
- `TRANSLATES_TO`: Text ist Uebersetzung eines anderen Textes.
- `DOCUMENTED_BY`: Objekt ist durch Dokumentation erklaert.
- `CONNECTED_TO`: Geraet oder Verbindung ist mit anderem Objekt verbunden.
- `TRIGGERS`: Variable oder Bedingung loest Alarm, Text oder Aktion aus.
- `REFERENCES`: Allgemeiner Querverweis, wenn der spezifische Beziehungstyp noch nicht bekannt ist.

Jede Edge soll mindestens `source_id`, `target_id`, `type` und optional `metadata` enthalten.

## 5. Beispielgraph ProTool

Ein ProTool-Projekt kann zunaechst aus CSV-Demodaten als Graph dargestellt werden:

```text
Project "Beispielprojekt"
  CONTAINS ProjectFile "MessageText.csv"

ProjectFile "MessageText.csv"
  DEFINES TextResource "Hydraulikpumpe überprüfen"

TextResource "Hydraulikpumpe überprüfen"
  DISPLAYS Device "OP7 preview"
  TRANSLATES_TO TextResource "Sprawdzić pompę hydrauliczną"
```

Der konkrete CSV-Inhalt bleibt Quelle. Der Graph beschreibt, welche fachlichen Objekte daraus entstehen und wie sie zusammenhaengen.

## 6. Beispielgraph PLC/HMI

Zielbild fuer spaetere PLC/HMI-Analyse:

```text
Variable "DB10.DBX48.3"
  READS_BY ProgramBlock "FC12"
  WRITTEN_BY ProgramBlock "FC37"
  TRIGGERS Alarm "Alarm 23"
  DISPLAYS TextResource "Hydraulikpumpe überprüfen"
  DOCUMENTED_BY DocumentationReference "Siemens manual or project note"
```

Die finalen Edge-Namen im Modell bleiben `READS` und `WRITES`; die Darstellung kann menschenlesbar als `read_by` oder `written_by` formuliert werden.

## 7. Speicherstrategie v1

Fuer v1 wird keine Graphdatenbank eingefuehrt.

Vorgesehene Strategie:

- JSON-kompatible Datenstruktur mit `nodes` und `edges`.
- In-Memory-Aufbau fuer Demo- und kleine Projektgraphen.
- Persistenz spaeter optional als JSON-Datei im lokalen Workspace.
- Spaeter optional SQLite fuer lokale Persistenz oder NetworkX fuer Analysefunktionen.
- Keine externe schwere Abhaengigkeit im ersten Schritt.

Diese Strategie passt zum lokalen, read-only Entwicklungsstand und verhindert fruehe Infrastrukturkomplexitaet.

## 8. API-Zielbild

Moegliche zukuenftige Endpoints:

```text
GET /assistant/engineering/graph/projects/{project_id}
GET /assistant/engineering/graph/nodes/{node_id}
GET /assistant/engineering/graph/search?q=...
GET /assistant/engineering/graph/impact/{node_id}
```

Diese Endpoints werden in diesem Architekturpapier nur skizziert und noch nicht implementiert.

## 9. Grenzen

- Der Graph ersetzt nicht TIA Portal, ProTool, STEP7 oder andere Engineering-Werkzeuge.
- HammerJarvis veraendert keine Produktionsprojekte automatisch.
- Der erste Graph-Ausbau bleibt read-only.
- Parser liefern Daten in den Graph, veraendern aber keine Quelldateien.
- Unsichere oder unvollstaendige Parser duerfen keine verbindlichen Engineering-Aussagen ohne Quellenhinweis erzeugen.

## 10. Naechster Implementierungsschritt

Empfohlener naechster Schritt:

1. Dataclasses oder Pydantic-Modelle fuer `GraphNode` und `GraphEdge` ergaenzen.
2. Einen einfachen In-Memory `GraphBuilder` implementieren.
3. Einen Demo-Graph aus den bestehenden ProTool-Demodaten erzeugen.
4. Read-only API fuer den Graph-Demo bereitstellen.
5. GUI-Visualisierung spaeter in einem separaten Schritt ergaenzen.

Der erste Implementierungsschritt sollte klein bleiben: Modelle, Builder, Demo-Daten und Tests. Keine neuen Parser und keine Graphdatenbank.

## Implemented v1 skeleton

Der erste Skeleton umfasst `GraphNode`, `GraphEdge`, `EngineeringGraph` und einen einfachen `GraphBuilder` fuer Demo-Daten. Die API stellt read-only Demo-Endpunkte fuer Projektgraph, Nodes, Suche und direkte Impact-Nachbarn bereit. Es wurden keine Siemens-Parser und keine Graphdatenbank eingefuehrt.
