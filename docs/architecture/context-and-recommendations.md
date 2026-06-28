# Context Engine + Recommendation Engine

## 1. Ziel

Hammer Jarvis soll nach v0.6.0 nicht nur Intents erkennen, sondern den aktiven Arbeitskontext nutzen und daraus sinnvolle Empfehlungen ableiten.

Der Benutzer soll nicht jedes Mal alle Informationen wiederholen müssen. Wenn ein Projekt, eine Datei, ein Panel oder eine Aufgabe aktiv ist, soll Jarvis diesen Kontext für nächste Vorschläge, Folgefragen und sichere Aktionen verwenden.

## 2. Problem

Bisher sind viele Module erreichbar, aber Jarvis merkt sich noch zu wenig:

- welches Projekt aktiv ist
- welche Datei betrachtet wird
- welches Panel gewählt ist
- welche Aufgabe gerade läuft
- welche Analyseergebnisse relevant sind

Ohne Kontext wirken Chat, Command Palette, Project Explorer, ProTool Assistant und Knowledge wie getrennte Werkzeuge. Folgekommandos wie "analysiere diese Datei", "zeige die Vorschau" oder "suche dazu Dokumentation" brauchen aber einen gemeinsamen Zustand.

## 3. Context Engine

Die Context Engine hält den aktiven Arbeitszustand.

Geplanter `ContextState`:

- `active_workspace`
- `active_project_id`
- `active_project_name`
- `active_project_path`
- `active_file`
- `active_file_type`
- `active_panel`
- `active_language`
- `last_intent`
- `last_search_query`
- `last_selected_node`
- `current_task`
- `updated_at`

Der Kontext bleibt explizit und kontrollierbar. Er darf helfen, Folgekommandos zu verstehen, aber keine Sicherheitsregeln umgehen.

## 4. Context Updates

Kontext soll aktualisiert werden durch:

- Intent Engine
- Project Explorer
- ProTool Assistant
- Command Palette
- spätere Voice Commands
- API

Beispiele:

- Project Explorer öffnet ein Projekt und setzt `active_project_id`, `active_project_name`, `active_project_path`.
- Klick auf `MessageText.csv` setzt `active_file` und `active_file_type`.
- Auswahl eines Panels setzt `active_panel`.
- Command Palette setzt `last_intent`.
- Knowledge-Suche setzt `last_search_query`.

## 5. Recommendation Engine

Die erste Recommendation Engine bleibt read-only und regelbasiert.

Sie erzeugt Empfehlungen aus:

- aktuellem Kontext
- Capabilities
- Project Explorer
- ProTool Analyseergebnissen
- Knowledge Status
- Systemstatus

Empfehlungen sind keine automatischen Aktionen. Sie sind Hinweise auf sinnvolle nächste Schritte und können später Intents vorbereiten.

## 6. Recommendation-Modell

JSON-kompatibles Modell:

```json
{
  "id": "...",
  "title": "...",
  "message": "...",
  "severity": "info|warning|critical",
  "source": "engineering|knowledge|system|voice",
  "intent": "...",
  "arguments": {},
  "read_only": true
}
```

Felder:

- `id`: stabile Empfehlung-ID.
- `title`: kurze Anzeigeüberschrift.
- `message`: verständliche Begründung.
- `severity`: Priorität der Empfehlung.
- `source`: fachliche Quelle.
- `intent`: optionaler Intent für eine mögliche Folgeaktion.
- `arguments`: vorbereitete Intent-Argumente.
- `read_only`: muss in v1 immer `true` sein.

## 7. Erste Empfehlungen v1

Mindestens:

- Kein aktives Projekt -> "Projekt öffnen"
- Aktives Engineering-Projekt -> "Projektdateien analysieren"
- ProTool CSV aktiv -> "ProTool Analyse starten"
- ProTool Analyse mit Issues -> "Panel-Vorschau prüfen"
- Knowledge leer -> "Dokumente indexieren"
- Voice nicht bereit -> "Voice-Status prüfen"

Die Empfehlungen sollen deterministisch sein. Keine AI-generierten Empfehlungen in v1.

## 8. GUI-Zielbild

Das Command Center zeigt:

- aktiven Kontext
- Empfehlungen
- Schnellaktionen
- reduzierte Statusanzeige

Bestehende Kacheln bleiben vorhanden, werden aber perspektivisch sekundär. Der Benutzer soll zuerst sehen: "Woran arbeite ich gerade?" und "Was ist der nächste sinnvolle Schritt?"

## 9. API-Zielbild

Geplante Endpoints:

```text
GET /assistant/context
POST /assistant/context/update
POST /assistant/context/reset
GET /assistant/recommendations
```

`GET /assistant/context` und `POST /assistant/context/reset` existieren bereits in v0.6.0 Teil 1. v0.6.1 ergänzt ein explizites Update und Empfehlungen.

## 10. Sicherheitsmodell

- Empfehlungen führen nichts automatisch aus.
- Empfehlungen sind read-only Hinweise.
- `YELLOW`/`RED` Aktionen dürfen nur vorbereitet werden.
- Keine Produktionsdaten verändern.
- Die Recommendation Engine darf das Permission-Modell nicht umgehen.

Wenn eine Empfehlung später eine riskante Aktion vorbereitet, muss der Intent weiterhin Bestätigung und Sicherheitsprüfung erzwingen.

## 11. Nicht-Ziele

- Keine AI-generierten Empfehlungen in v1.
- Keine Hintergrundautomatisierung.
- Keine Voice-v2.
- Kein Umbau aller Module.
- Keine automatische Ausführung von Empfehlungen.

## 12. Nächster Implementierungsschritt

V1 sollte klein und testbar bleiben:

1. `ContextState` erweitern.
2. `ContextStore` update/reset stabilisieren.
3. `RecommendationEngine` statisch/regelkodiert implementieren.
4. `GET /assistant/recommendations` ergänzen.
5. `POST /assistant/context/update` ergänzen.
6. Command Center zeigt Kontext und Empfehlungen.
7. Tests für ContextStore, Empfehlungen, API und Dashboard.

Der erste Schritt soll keine Voice-v2-Logik, keine AI-Empfehlungen und keine Hintergrundautomatisierung einführen.

