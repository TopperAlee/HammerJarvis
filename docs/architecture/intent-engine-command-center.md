# Intent Engine + Command Center

## 1. Ziel

Hammer Jarvis soll nicht mehr primär über einzelne Dashboard-Kacheln bedient werden, sondern über eine gemeinsame Intent-Schicht.

Langfristig sollen alle Eingabearten denselben Intent erzeugen:

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

Das Ziel ist ein einheitliches Bedienmodell: Jede Eingabe wird normalisiert, in eine Absicht übersetzt, mit Kontext angereichert, sicher bewertet und dann an die passende Fähigkeit weitergeleitet.

## 2. Problem

Die aktuelle GUI ist funktional stark, aber überfrachtet. Mit jedem neuen Modul entstehen weitere Kacheln, Buttons, Spezialfälle und Direktverbindungen zu Backend-Endpunkten.

Neue Module erhöhen dadurch die Komplexität:

- Engineering Workspace
- Engineering Object Graph
- Project Explorer
- ProTool Assistant
- Knowledge
- Home Assistant
- Voice
- Datei- und Web-Werkzeuge

Ohne Intent-Schicht entsteht doppelte Logik in GUI, Chat und Voice. Dieselbe Aktion müsste mehrfach erkannt, validiert, geroutet und erklärt werden. Das erschwert Tests, Sicherheit und Benutzerführung.

## 3. Grundprinzip

```text
Input
  ↓
Intent Parser
  ↓
Context Engine
  ↓
Decision Engine
  ↓
Capability Registry
  ↓
Action Resolver
  ↓
Tool / Skill / Module
  ↓
Response Builder
```

Die Intent Engine trennt Eingabe, Entscheidung und Ausführung. Eingaben werden nicht direkt an Tools geschickt, sondern zuerst als strukturierte Absicht beschrieben.

## 4. Intent-Modell

Erstes JSON-kompatibles Modell:

```json
{
  "intent": "engineering.project.open",
  "source": "voice|chat|command_palette|button|api",
  "confidence": 0.0,
  "arguments": {},
  "context": {},
  "requires_confirmation": false,
  "risk": "GREEN|YELLOW|RED"
}
```

Felder:

- `intent`: stabile maschinenlesbare Absicht.
- `source`: Ursprung der Eingabe.
- `confidence`: Sicherheit der Erkennung.
- `arguments`: explizite Parameter der Eingabe.
- `context`: aktive Arbeitskontexte.
- `requires_confirmation`: ob eine Bestätigung erforderlich ist.
- `risk`: Sicherheitsklassifikation.

## 5. Erste Intent-Gruppen

### Engineering

- `engineering.workspace.open`
- `engineering.project.open`
- `engineering.project.search`
- `engineering.protool.analyze`
- `engineering.panel.preview`

### Knowledge

- `knowledge.search`
- `knowledge.open_document`
- `knowledge.summarize`

### Automation

- `automation.homeassistant.prepare`
- `automation.homeassistant.execute`

### Assistant

- `assistant.status`
- `assistant.help`
- `assistant.switch_mode`

### Development

- `development.git.status`
- `development.tests.run`

## 6. Context Engine

Die Context Engine hält aktive Kontexte, damit Folgekommandos ohne Wiederholung funktionieren.

Wichtige Kontexte:

- `active_project_id`
- `active_project_name`
- `active_file`
- `active_panel`
- `active_language`
- `active_workspace`
- `last_search_query`
- `last_selected_node`
- `current_task`

Beispiel:

```text
Öffne die Retro-Presse.
Zeig mir die Alarme.
Übersetze die fehlenden.
```

Der zweite und dritte Satz sind nur sinnvoll, wenn Jarvis das aktive Projekt, die aktuelle Ansicht und die aktuelle Aufgabe kennt.

## 7. Capability Registry

Jarvis soll seine eigenen Fähigkeiten kennen. Die Capability Registry beschreibt, welche Funktionen vorhanden, sichtbar und sicher nutzbar sind.

Felder:

- `capability_id`
- `name`
- `module`
- `plugin`
- `status`
- `implemented_since`
- `gui_available`
- `api_available`
- `voice_ready`
- `risk_level`
- `read_only`

Beispiel:

```json
{
  "id": "engineering.protool.preview",
  "name": "ProTool Panel Preview",
  "module": "engineering",
  "plugin": "protool",
  "status": "implemented",
  "implemented_since": "v0.3.1",
  "gui_available": true,
  "api_available": true,
  "voice_ready": false,
  "risk_level": "GREEN",
  "read_only": true
}
```

Die Registry ist Grundlage für Command Palette, Hilfe, Voice-Fähigkeiten und Sicherheitsprüfung.

## 8. Command Center

Das Command Center wird die neue UX-Schicht:

- reduzierte Startseite
- zentrale Eingabezeile
- Command Palette mit `Ctrl+K`
- Modulauswahl über Intents
- Statusleiste
- zuletzt genutzte Projekte
- adaptive Workspaces

Statt immer mehr Kacheln zu zeigen, soll Hammer Jarvis kontextbezogene Aktionen anbieten. Die bestehenden Module bleiben erreichbar, werden aber zunehmend über Intents auffindbar und bedienbar.

## 9. Event Bus

Zielarchitektur ist ein lokales In-Memory-Event-System. Es soll lose Kopplung zwischen GUI, Kontext, Modulen und Aktionen ermöglichen.

Beispiele:

- `engineering.project.opened`
- `engineering.file.selected`
- `intent.executed`
- `context.changed`
- `capability.invoked`

Der Event Bus wird in diesem Meilenstein noch nicht implementiert. Er beschreibt die spätere Richtung für modulare Interaktion.

## 10. Voice Integration

Voice erzeugt langfristig dieselben Intents wie die Command Palette.

Ziel:

- Wake Word und Double Clap lösen nur Listening aus.
- Speech Recognition erzeugt Text.
- Intent Parser interpretiert Text.
- Längere Eingaben werden über Stille-Erkennung sauber abgeschlossen.
- Visuelles Feedback zeigt: "Ich höre", "Sprich weiter", "Verarbeite".

Voice darf keine Sonderlogik bekommen, die Sicherheitsregeln umgeht. Ein Sprachbefehl und ein Button müssen denselben Intent und dieselbe Risikobewertung erzeugen.

## 11. Sicherheitsmodell

- Read-only Intents sind `GREEN`.
- Home Assistant Schreibaktionen sind `YELLOW` und brauchen Bestätigung.
- PLC Write, Datei löschen und echte E-Mail senden sind `RED` und blockiert.
- Die Intent Engine darf das Sicherheitsmodell nicht umgehen.

Sicherheitsbewertung ist Teil der Intent-Verarbeitung und nicht erst Teil der Tool-Ausführung.

## 12. API-Zielbild

Zukünftige Endpoints:

```text
POST /assistant/intent/parse
POST /assistant/intent/execute
GET /assistant/context
POST /assistant/context/reset
GET /assistant/commands
GET /assistant/capabilities
```

Diese Endpoints werden in diesem Architekturpapier nur skizziert und noch nicht implementiert.

## 13. GUI-Zielbild

- Command Center als Startansicht.
- Bestehende Module bleiben erreichbar.
- Neue Command Palette.
- Keine bestehende Funktion entfernen.
- UX schrittweise umstellen.

Die Umstellung muss inkrementell erfolgen. Das vorhandene Dashboard bleibt funktionsfähig, während Command Palette und adaptive Workspaces daneben aufgebaut werden.

## 14. Nächster Implementierungsschritt

V1 sollte klein bleiben:

- `IntentRequest` / `IntentResult` Modelle.
- Einfache regelbasierte Intent-Erkennung.
- `ContextStore` in-memory.
- `CapabilityRegistry` statisch.
- `POST /assistant/intent/parse`.
- `GET /assistant/commands`.
- `GET /assistant/capabilities`.
- Command Palette im Dashboard.
- Keine Voice-v2-Implementierung in diesem Schritt.

Der erste Schritt schafft Struktur und Tests, ohne alle Module gleichzeitig umzubauen.

## 15. Nicht-Ziele

- Kein LLM-basierter Intent Parser in v1.
- Kein Double Clap in v1.
- Kein Umbau aller Module auf einmal.
- Keine entfernten Dashboard-Funktionen.
- Keine neuen gefährlichen Aktionen.

