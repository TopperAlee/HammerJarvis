# Hammer Jarvis Masterplan

## 1. Mission

Hammer Jarvis ist ein lokales AI Engineering Operating System für Automatisierungstechnik.

Hammer Jarvis ist nicht nur ein Chatbot und nicht nur ein HMI-Tool. Das Ziel ist eine zentrale Arbeitsoberfläche für Engineering: lokal, nachvollziehbar, kontrollierbar und erweiterbar.

Der Engineer soll Hammer Jarvis nutzen können, um Projekte zu verstehen, technische Zusammenhänge zu erkennen, Wissen zu finden, Entscheidungen vorzubereiten und sichere Aktionen auszuführen.

## 2. Produktphilosophie

Jede neue Funktion muss mindestens eine dieser Fragen mit Ja beantworten:

- Hilft sie dem Engineer schneller zu verstehen?
- Hilft sie dem Engineer schneller zu entscheiden?
- Hilft sie dem Engineer schneller zu handeln?

Wenn eine Funktion keine dieser Fragen klar beantwortet, gehört sie nicht in den Kern von Hammer Jarvis.

## 3. Grundprinzipien

- Local First
- Privacy First
- Read-only by default
- Human approval for critical actions
- AI assists, never silently changes production data
- Engineering Graph first
- Intent first
- Context aware
- Voice-capable by design

Diese Prinzipien gelten für Engineering, Knowledge, Automation, Assistant-Funktionen und GUI. Kritische Aktionen benötigen eine explizite Sicherheitsbewertung und eine bewusste Bestätigung durch den Benutzer.

## 4. Kernsysteme

### Intent Engine

Die Intent Engine übersetzt Eingaben aus Chat, Voice, Buttons, API oder anderen Quellen in strukturierte Absichten. Sie entscheidet nicht frei, sondern routet bekannte Domänen deterministisch an die passenden Tools.

### Context Engine

Die Context Engine hält den aktuellen Arbeitskontext: Projekt, Datei, Aufgabe, Sprache, Panel, Variable, Alarm oder laufende Analyse. Dadurch kann Jarvis Folgefragen korrekt einordnen.

### Engineering Knowledge Graph

Der Engineering Knowledge Graph verbindet Projekte, Dateien, HMI-Texte, Alarme, Variablen, PLC-Bausteine, Dokumentation und Querverweise. Er ist die Grundlage für Suche, Impact-Analyse, Reports und AI-Abfragen.

### Knowledge Layer

Der Knowledge Layer verwaltet lokale Dokumente, Handbücher, Notizen, Lessons Learned und Maschinendokumentation. Quellen bleiben nachvollziehbar und werden getrennt von Memory und Engineering-Objekten behandelt.

### Automation Layer

Die Automation Layer kapselt lokale Tools wie Python, PowerShell, Git, Home Assistant und später weitere Systeme. Read-only ist Standard; schreibende oder produktionsrelevante Aktionen brauchen Sicherheitskonzept und Bestätigung.

### Adaptive GUI

Die GUI ist kein statisches Dashboard, sondern langfristig ein adaptiver Workspace. Sie zeigt kontextbezogene Werkzeuge und Ansichten, statt alle Funktionen gleichzeitig sichtbar zu machen.

### Voice Interaction

Voice ist ein Bedienkanal für dieselbe Intent-Struktur wie Chat und Buttons. Sprache soll lokale Workflows schneller machen, aber keine Sicherheitsregeln umgehen.

## 5. Interaction Model

Alle Eingaben laufen später über dieselbe Intent-Struktur:

- Chat
- Voice
- Command Palette
- Buttons
- API
- Wake Word
- Double Clap
- Keyboard Shortcut
- Stream Deck
- Home Assistant Event

Beispiel:

```json
{
  "intent": "engineering.project.open",
  "project": "Retro Presse"
}
```

Das Ziel ist ein einheitlicher Weg:

```text
Input
  ↓
Intent
  ↓
Action
  ↓
Result
```

Dadurch bleibt das System konsistent. Ein Button, ein Sprachbefehl und ein API-Aufruf sollen dieselbe Absicht erzeugen und denselben Sicherheitsregeln folgen.

## 6. Context Engine

Jarvis soll aktive Kontexte halten:

- aktuelles Projekt
- aktive Datei
- aktives Panel
- aktuelle Sprache
- aktuelle Aufgabe
- zuletzt betrachtete Variable
- zuletzt betrachteter Alarm
- laufende Analyse

Beispieldialog:

```text
Benutzer: Öffne die Retro-Presse.
Jarvis: Projekt Retro Presse ist aktiv.

Benutzer: Zeig mir die Alarme.
Jarvis: Zeigt Alarme aus dem aktiven Projekt.

Benutzer: Übersetze die fehlenden.
Jarvis: Nutzt aktives Projekt, aktive Sprache und vorherige Alarmansicht.
```

Jarvis soll Kontext behalten, aber sichtbar und kontrollierbar. Kontext darf nie dazu führen, dass kritische Aktionen ohne Bestätigung ausgeführt werden.

## 7. Engineering Knowledge Graph

Langfristig soll der Engineering Knowledge Graph folgende Bereiche verbinden:

- PLC
- HMI
- Variablen
- Alarme
- Texte
- Dokumentation
- Git-Historie
- Tickets
- Lessons Learned
- Wartungsprotokolle

Der Graph beantwortet Fragen wie:

- Welche HMI-Texte hängen an dieser Variable?
- Welche Bausteine lesen oder schreiben dieses Signal?
- Welche Alarme werden durch diese Bedingung ausgelöst?
- Welche Dokumentation erklärt dieses Objekt?
- Welche Änderungshistorie gibt es zu diesem Bereich?

Der Graph ersetzt keine Engineering-Tools. Er macht Beziehungen sichtbar und durchsuchbar.

## 8. GUI Vision

Jarvis soll weniger überladen werden:

- Command Center
- adaptive Workspaces
- Engineering Mode
- Home Mode
- Development Mode
- Research Mode
- Focus Mode
- globale Command Palette mit `Ctrl+K`

Die GUI soll kontextbezogene Werkzeuge anzeigen. Wenn ein Projekt aktiv ist, stehen Engineering-Aktionen im Vordergrund. Wenn eine Datei aktiv ist, stehen Analyse, Preview, Eigenschaften und relevante Querverweise im Vordergrund.

## 9. Voice Vision

Langfristige Voice-Ziele:

- Wake Word
- Double Clap als optionaler lokaler Wake Trigger
- Nutzer aussprechen lassen
- Stille-Erkennung
- visuelles Feedback: "Ich höre", "Sprich weiter", "Verarbeite"
- alle Module langfristig per Sprache bedienbar

Voice bleibt lokal-first. Cloud-Sprache ist keine Pflichtabhängigkeit. Der Voice-Pfad erzeugt dieselben Intents wie Chat, Buttons oder API.

## 10. Roadmap Tracks

### Engineering Track

Project Explorer, Engineering Object Graph, ProTool Importer, WinCC flexible, TIA, STEP7, PLC Diagnostics und Translation Studio.

### Interaction Track

Intent Engine, Command Palette, Voice Interaction v2, Wake-Flow, Double Clap und konsistente Folgekommandos.

### Knowledge Track

Lokale Dokumente, Manuals, Normen, Lessons Learned, Memory, Quellenanzeige und Knowledge-Kontext.

### Automation Track

Python, PowerShell, Git, Home Assistant, lokale Skripte, sichere Aktionen und langfristig kontrollierte Remote-Systeme.

### UX Track

Command Center, adaptive Workspaces, Focus Mode, Engineering Mode und reduzierte, kontextbezogene Oberfläche.

### Platform Track

Plugin-System, Konfiguration, Sicherheit, Performance, Logging, Settings, Testbarkeit und lokale Betriebsfähigkeit.

## 11. Release-Roadmap

Aktueller Stand:

- v0.3.1 ProTool Assistant / Engineering Foundation
- v0.4.1 Engineering Workspace + Object Graph
- v0.5.0 Project Explorer Foundation

Nächste geplante Meilensteine:

- v0.6.0 UX Command Center + Intent Architecture
- v0.7.0 Voice Interaction v2
- v0.8.0 ProTool Importer
- v0.9.0 Translation Studio
- v1.0 Engineering OS

## 12. Definition of Done

Ein neues Modul gilt erst als fertig, wenn:

- Architektur dokumentiert
- Tests vorhanden
- API vorhanden
- GUI integriert
- Intent definiert
- Voice-Bedienpfad möglich
- Security/Read-only bewertet
- Dokumentation aktualisiert

Falls ein Punkt für einen frühen Milestone bewusst nicht gilt, muss diese Abweichung dokumentiert sein.

## 13. Nicht-Ziele

- Kein Ersatz für TIA Portal
- Kein automatisches Ändern von Produktionsprojekten
- Kein PLC-Schreiben ohne neues Sicherheitskonzept
- Keine Cloud-Abhängigkeit als Pflicht
- Keine geheimen oder unkontrollierten Hintergrundaktionen

Hammer Jarvis ist ein lokales Assistenz- und Analyse-System. Es soll Engineering-Arbeit unterstützen, nicht unkontrolliert übernehmen.

