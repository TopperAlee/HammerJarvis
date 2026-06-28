# Engineering Project Explorer

## 1. Ziel

Der Engineering Project Explorer soll reale Engineering-Projektordner einlesen und als strukturierte Project-/Object-Graph-Sicht darstellen. Er baut auf dem Engineering Workspace und dem Engineering Object Graph auf.

Ziel ist eine gemeinsame read-only Projektsicht, in der HammerJarvis technische Dateien erkennt, klassifiziert und fuer spaetere Analysefunktionen vorbereitet. Dateien bleiben Quellen; fachliche Objekte werden schrittweise als Nodes und Edges in den Engineering Object Graph uebernommen.

## 2. Scope v0.5.0

Der Scope fuer v0.5.0 ist bewusst begrenzt:

- Ordner auswaehlen oder Projektpfad eingeben.
- Projektdateien im erlaubten lokalen Dateisystem erkennen.
- ProTool-CSV-Dateien klassifizieren.
- Projektbaum im Engineering Workspace darstellen.
- Erkannte Dateien als `ProjectFile`-Knoten in den Engineering Object Graph uebernehmen.
- Noch keine CSV-Inhalte vollstaendig parsen.
- Read-only Analyse ohne Veraenderung der Quelldateien.

Der Project Explorer liefert damit die Grundlage fuer spaetere Parser, Reports und Impact-Analysen.

## 3. Nicht-Ziele

Nicht Bestandteil von v0.5.0:

- Keine Datei veraendern.
- Keine Uebersetzung.
- Keine TIA-Portal-Projektparser.
- Keine STEP7-Classic-Parser.
- Keine Graphdatenbank.
- Keine automatische Migration oder Reparatur alter Engineering-Projekte.

## 4. Gemeinsames Modell

Der Project Explorer nutzt das bestehende Engineering-Modell als gemeinsame Zwischenschicht:

- `Project`: repraesentiert den geoeffneten Projektordner oder Projektausschnitt.
- `ProjectFile`: repraesentiert erkannte Dateien, ihren Typ, Pfad und Modulbezug.
- `TextResource`: entsteht spaeter aus HMI-Textparsern wie ProTool, WinCC flexible oder Translation-Exports.
- `Alarm`: entsteht spaeter aus Alarmtexten, Meldelisten oder PLC/HMI-Verknuepfungen.
- `Variable`: entsteht spaeter aus Variablenlisten, Symboltabellen oder PLC-Exports.

Parser sollen zukuenftig fachliche Objekte erzeugen und in den Engineering Object Graph einspeisen. Der Project Explorer v0.5.0 erzeugt zunaechst nur `Project`- und `ProjectFile`-Strukturen sowie Graph-Knoten fuer erkannte Dateien.

## 5. ProTool-Erkennung v1

Die erste Klassifizierung konzentriert sich auf typische ProTool-CSV-Exporte:

- `MessageText.csv` -> HMI-Meldetexte
- `InfoHelpText.csv` -> Hilfetexte
- `AlarmText.csv` -> Alarmtexte
- `TextList.csv` -> Textlisten
- `RecipeText.csv` -> Rezepttexte
- `Variables.csv` -> Variablen

Die Klassifizierung soll case-insensitive arbeiten und bekannte Namensvarianten tolerieren, ohne Dateiinhalte zu veraendern. Unbekannte CSV-Dateien bleiben sichtbar, werden aber als `unknown_csv` oder `other` markiert.

## 6. API-Zielbild

Moegliche read-only Endpoints:

```text
POST /assistant/engineering/projects/open
GET /assistant/engineering/projects/{project_id}
GET /assistant/engineering/projects/{project_id}/tree
GET /assistant/engineering/projects/{project_id}/files
POST /assistant/engineering/projects/{project_id}/analyze
```

`open` nimmt einen lokalen Projektpfad entgegen und erzeugt eine Project-Struktur.  
`tree` liefert die hierarchische Explorer-Ansicht.  
`files` liefert eine flache Liste erkannter Dateien mit Klassifikation.  
`analyze` startet spaeter read-only Analysefunktionen fuer erkannte Module.

## 7. GUI-Zielbild

Der Engineering Workspace erhaelt eine reale Project-Explorer-Anbindung:

- Links: Project Explorer mit geoeffnetem Projekt, Ordnern und klassifizierten Dateien.
- Mitte: Datei- oder Analyseansicht fuer die aktuell gewaehlte Datei.
- Rechts: Eigenschaften wie Dateityp, Modul, Pfad, Klassifikation, Encoding-Hinweise und Graph-Beziehungen.

Ein Klick auf eine ProTool-CSV soll die bestehende ProTool-Analyse oder Panel-Preview vorbereiten. Die bestehende ProTool-Funktion bleibt erhalten und wird nicht dupliziert.

## 8. Sicherheitsprinzipien

- Read-only: keine Quelldatei wird veraendert.
- Keine automatischen Aenderungen an Engineering-Projekten.
- Erlaubte Pfade muessen beachtet werden.
- Zugriff ausserhalb erlaubter Verzeichnisse muss mit klarer Fehlermeldung abgelehnt werden.
- Reports und UI duerfen keine Secrets oder sensiblen Tokens anzeigen.
- Parser duerfen Projektdateien nur lesen und muessen Fehler isoliert melden.

## 9. Implementierungsschritte

Empfohlene Reihenfolge:

1. `ProjectScanner`: scannt einen erlaubten Projektordner rekursiv mit Limits.
2. `FileClassifier`: klassifiziert erkannte Dateien, zuerst ProTool-CSV-Dateien.
3. Demo/Real Project Tree: erzeugt eine einheitliche Baumstruktur fuer API und Dashboard.
4. API fuer `open project`, `tree` und `files`.
5. GUI-Anbindung im Engineering Workspace.
6. Tests fuer Pfadsicherheit, Klassifizierung, grosse Ordner, API und Dashboard.

Der Object Graph wird im ersten Schritt nur mit `Project`- und `ProjectFile`-Nodes ergaenzt. Fachliche Inhaltsobjekte wie `TextResource`, `Alarm` oder `Variable` folgen in spaeteren Parser-Milestones.

## 10. Risiken

- Grosse Projektordner koennen Scans verlangsamen oder zu viele Dateien liefern.
- Exportnamen sind uneinheitlich und koennen kundenspezifisch abweichen.
- CSV-Encoding-Probleme koennen schon bei der Klassifizierung sichtbar werden.
- Browser-Pfadlimits verhindern echte lokale Pfadauswahl; manuelle Pfade oder Backend-gestuetzte Auswahl bleiben notwendig.
- OneDrive- oder Netzlaufwerk-Platzhalter koennen scheinbar vorhandene Dateien liefern, die lokal nicht lesbar sind.

