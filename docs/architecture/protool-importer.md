# ProTool Importer

## 1. Ziel

Der ProTool Importer ist die erste vollstaendige Engineering-Import-Pipeline in HammerJarvis. Er baut auf Engineering Workspace, Engineering Object Graph und Project Explorer auf.

Der Importer liest ProTool-CSV-Dateien read-only und erzeugt daraus Engineering-Objekte. CSV bleibt ein internes Eingabeformat des Importers:

- Keine GUI kennt CSV-Strukturen.
- Keine AI kennt CSV-Strukturen.
- Nur der Importer kennt CSV-Spalten, Encoding, Delimiter und ProTool-Sonderzeilen.

Nach dem Import arbeiten alle nachgelagerten Funktionen auf Engineering-Objekten und Graph-Beziehungen.

## 2. Architektur

```text
Filesystem
  ↓
Scanner
  ↓
Classifier
  ↓
Importer
  ↓
Engineering Object Graph
  ↓
Search
Translation
Preview
AI
```

Der Scanner findet Dateien. Der Classifier erkennt ProTool-Dateitypen. Der Importer liest nur die klassifizierten ProTool-Dateien und erzeugt Nodes und Edges im Engineering Object Graph. Suche, Uebersetzung, Vorschau und AI-Kontext arbeiten danach ausschliesslich auf Graph-Objekten.

## 3. Importierte Objekte

Erste importierte Objektarten:

- `Project`
- `ProjectFile`
- `TextResource`
- `Language`
- `Placeholder`
- `PanelPreview`
- `ImportSession`

`ImportSession` dokumentiert Importzeitpunkt, Quelle, Encoding, Delimiter, Paneltyp und technische Hinweise. Die Session ist wichtig, damit Reports nachvollziehbar bleiben.

## 4. TextResource

`TextResource` ist das zentrale Objekt fuer ProTool-HMI-Texte.

Pflichtfelder:

- `id`: stabile Text-ID im Graph.
- `name`: kurzer Anzeigename oder abgeleiteter Bezeichner.
- `text`: originaler Textinhalt aus der CSV.
- `language`: erkannte oder konfigurierte Sprache.
- `row`: CSV-Zeile.
- `panel`: Zielpanel, z. B. `OP7`.
- `preview`: gerenderte Panel-Zeilen.
- `truncated`: ob die Vorschau abgeschnitten wurde.
- `placeholders`: erkannte Platzhalter wie `<###>`, `%d`, `%s`, `{0}`.
- `metadata`: JSON-kompatible Zusatzdaten wie Quelldatei, Encoding, Delimiter, Textspalte oder Importhinweise.

Der Text bleibt original. Der Importer normalisiert nur Struktur und Metadaten, nicht den Inhalt.

## 5. Beziehungen

Erste Graph-Beziehungen:

```text
Project
  CONTAINS
ProjectFile

ProjectFile
  DEFINES
TextResource

TextResource
  HAS_LANGUAGE
Language

TextResource
  HAS_PLACEHOLDER
Placeholder

TextResource
  RENDERED_AS
PanelPreview
```

Diese Beziehungen erlauben spaeter Suche, Impact-Analyse, Translation-QA und nachvollziehbare Reports.

## 6. Importprozess

```text
CSV lesen
  ↓
Encoding
  ↓
Delimiter
  ↓
Preview
  ↓
Placeholder
  ↓
TextResource erzeugen
  ↓
GraphNodes
  ↓
GraphEdges
```

Der Importprozess verwendet bestehende ProTool-CSV-Lese- und Validierungsbausteine, dupliziert aber keine Validierungslogik. Fehler einzelner Zeilen duerfen den gesamten Import nicht unkontrolliert abbrechen; sie werden als Importhinweise oder Issues an der `ImportSession` dokumentiert.

## 7. Read-only

Der ProTool Importer bleibt strikt read-only:

- Keine CSV veraendern.
- Keine Uebersetzung erzeugen.
- Kein Export schreiben.
- Keine Projektdateien anpassen.
- Keine automatische Reparatur.

Der Import erzeugt nur interne Engineering-Objekte und Reports.

## 8. API-Zielbild

Moegliche read-only Endpoints:

```text
POST /assistant/protool/import
GET /assistant/protool/projects/{id}
GET /assistant/protool/texts
GET /assistant/protool/text/{id}
GET /assistant/protool/search
```

Diese Endpoints werden in diesem Architekturpapier nur skizziert und noch nicht implementiert.

## 9. GUI

Zielbild im Engineering Workspace:

```text
Project Explorer
  ↓
MessageText.csv
  ↓
Import
  ↓
Textliste
  ↓
Panel Preview
```

Der Nutzer waehlt im Project Explorer eine erkannte ProTool-CSV. Die GUI startet spaeter einen Import und zeigt danach Textliste, Issues, Platzhalter und Panel Preview aus Engineering-Objekten an. Die GUI soll keine CSV-Spaltenlogik kennen.

## 10. Risiken

- Grosse CSV-Dateien koennen Importzeit und Speicherbedarf erhoehen.
- Mehrere Sprachen in einer Datei koennen Sprachkopfzeilen, leere Zeilen und Sonderformate enthalten.
- Encoding-Probleme koennen Zeichen falsch interpretieren oder nicht kodierbare Texte sichtbar machen.
- Placeholder koennen je Sprache fehlen, beschaedigt oder vertauscht sein.
- Mehrere Panels koennen unterschiedliche Breiten, Hoehen und Vorschaugrenzen erfordern.

## 11. Naechster Schritt

Empfohlene spaetere Implementierung:

1. `ProToolImporter`
2. `TextResourceBuilder`
3. `PlaceholderBuilder`
4. `PreviewBuilder`
5. `GraphBuilder`-Integration fuer ProTool-Objekte
6. Tests fuer Encoding, Delimiter, Sprachzeilen, Placeholder, Preview und Graph-Beziehungen

Der erste Implementierungsschritt sollte auf einer einzelnen ProTool-CSV starten und daraus `TextResource`, `Language`, `Placeholder`, `PanelPreview` und `ImportSession` als GraphNodes erzeugen.

