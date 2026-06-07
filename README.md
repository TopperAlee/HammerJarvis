# Hammer Jarvis

Hammer Jarvis ist ein lokaler, Windows-first Backend-Prototyp fuer einen persoenlichen AI-Assistenten.
Version 0.1 verbindet sich mit Home Assistant ueber die REST API und stellt lokale FastAPI-Endpunkte bereit.

## Zweck des Projekts

Das Projekt soll lokale Assistant-Funktionen bereitstellen, ohne Cloud-Deployment, Docker, Datenbank, Voice-Control oder autonome Aktionen.
In v0.1 gibt es einfache regelbasierte Chat-Kommandos und Home-Assistant-Werkzeuge fuer Statusabfragen, Suche, Energie-/Leistungswerte und bestaetigungspflichtiges Schalten.

## Voraussetzungen

- Windows
- PowerShell
- Python 3.11 oder neuer
- Home Assistant unter `http://192.168.0.15:8123`
- Home Assistant Long-Lived Access Token

## Windows PowerShell Setup

```powershell
cd D:\Dev\projects\HammerJarvis
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Lokale Konfiguration

Erstelle eine lokale `.env` aus der Beispieldatei:

```powershell
Copy-Item .env.example .env
```

Trage danach in `.env` deinen Home Assistant Long-Lived Access Token ein:

```text
HOME_ASSISTANT_URL=http://192.168.0.15:8123
HOME_ASSISTANT_TOKEN=your_long_lived_access_token_here
ECOFLOW_BATTERY_POWER_SIGN=unknown
```

Die echte `.env` darf nicht committed werden.

## Server Starten

```powershell
.\scripts\start-jarvis.ps1
```

Der dokumentierte Entwicklungsport ist `8001`, weil `8000` auf diesem Windows-Rechner haeufig bereits belegt ist.
Wenn `8000` frei ist, kann der Server alternativ manuell mit `uvicorn app.main:app --reload --port 8000` gestartet werden.

## Browser URLs

- API Startseite: `http://127.0.0.1:8001/`
- Swagger UI: `http://127.0.0.1:8001/docs`
- Home Assistant Entities: `http://127.0.0.1:8001/ha/entities`
- Nicht verfuegbare Entities: `http://127.0.0.1:8001/ha/unavailable`
- Klassifizierte Home Assistant Probleme: `http://127.0.0.1:8001/ha/problems`
- EcoFlow Diagnose: `http://127.0.0.1:8001/ha/ecoflow`
- EcoFlow Energieuebersicht: `http://127.0.0.1:8001/ha/ecoflow/energy`
- Energie-/Leistungswerte: `http://127.0.0.1:8001/ha/power`

## Dashboard oeffnen

Das lokale Dashboard ist nach dem Serverstart im Browser erreichbar:

```text
http://127.0.0.1:8001/dashboard
```

## Sprachsteuerung

Oeffne das lokale Dashboard unter `http://127.0.0.1:8001/dashboard`.
Klicke auf `Sprechen`, erlaube den Mikrofonzugriff im Browser und sprich einen Befehl.
Jarvis zeigt den erkannten Befehl und die Antwort im Dashboard an und gibt die Antwort per Sprachausgabe aus, wenn die Sprachausgabe eingeschaltet ist.

Die Sprachsteuerung nutzt die Web Speech API des Browsers.
Falls die Spracherkennung nicht verfügbar ist, verwende Chrome oder Edge.
Es gibt in v0.2 noch kein Wake Word und keinen Always-Listening-Modus.

## Hammer Jarvis Agent v0.3

Der neue Agent-Orchestrator ist ueber diesen lokalen Endpunkt erreichbar:

```text
POST http://127.0.0.1:8001/assistant/chat
```

`/chat` bleibt als regelbasierter Bestandsendpunkt erhalten.
`/assistant/chat` nutzt eine Tool Registry und bereitet Hammer Jarvis auf mehrere Werkzeugbereiche vor.

- Smart Home und EcoFlow nutzen echte lokale Home-Assistant-Daten.
- E-Mail und Kalender sind in v0.3 sichere Mock-Werkzeuge.
- Eine echte Gmail-, Outlook- oder Kalenderverbindung kommt spaeter.
- Schreibaktionen brauchen eine Bestaetigung.
- RED-Aktionen wie echtes E-Mail-Senden oder PLC-Schreiben sind blockiert.
- Die optionale LLM-Anbindung ist vorbereitet. Ohne `OPENAI_API_KEY` laeuft der Agent im lokalen `rule_based_fallback`.

## Produktivitaets-Integrationen

Hammer Jarvis v0.3 enthaelt eine lokale Provider-Architektur fuer E-Mail- und Kalenderfunktionen.
Die Provider sind vorbereitet, aber noch nicht mit echten Konten verbunden.

- Gmail: vorbereitet fuer die Gmail API, OAuth ist noch nicht aktiv.
- Outlook Mail: vorbereitet fuer Microsoft Graph, OAuth ist noch nicht aktiv.
- Outlook Kalender: vorbereitet fuer Microsoft Graph, OAuth ist noch nicht aktiv.
- Google Kalender: vorbereitet fuer die Google Calendar API, OAuth ist noch nicht aktiv.
- TimeTree: nur als Import-/Export- oder ICS-Quelle vorbereitet, weil die oeffentliche Entwickler-API nicht mehr regulaer verfuegbar ist.

Diese lokalen Endpunkte zeigen den aktuellen Integrationsstatus:

```text
GET http://127.0.0.1:8001/assistant/providers
GET http://127.0.0.1:8001/assistant/calendar/today
GET http://127.0.0.1:8001/assistant/email/search?q=example
GET http://127.0.0.1:8001/assistant/timetree/status
```

E-Mail-Suche und Kalenderabfragen liefern aktuell sichere Mock-Antworten.
Echte E-Mails werden nicht gesendet.
Kalendereintraege werden noch nicht real erstellt.
Schreibende Aktionen bleiben bestaetigungspflichtig oder blockiert, bis die jeweiligen Provider sicher konfiguriert sind.

## Gmail verbinden

Hammer Jarvis v0.4 kann Gmail lokal und read-only ueber die offizielle Gmail API durchsuchen.
Es werden keine E-Mails gesendet und in diesem Schritt noch keine echten Entwuerfe erstellt.

So richtest du Gmail ein:

1. Oeffne die Google Cloud Console und erstelle oder waehle ein Projekt.
2. Aktiviere die Gmail API fuer dieses Projekt.
3. Konfiguriere den OAuth Consent Screen. Fuer ein privates Konto reicht normalerweise `External` mit Testnutzern; bei Google Workspace kann `Internal` passen.
4. Erstelle eine OAuth Client ID vom Typ `Desktop App`.
5. Lade die JSON-Datei herunter.
6. Speichere sie lokal als:

```text
app/secrets/google/gmail_credentials.json
```

7. Setze in deiner lokalen `.env`:

```text
GMAIL_ENABLED=true
GOOGLE_GMAIL_CREDENTIALS_FILE=app/secrets/google/gmail_credentials.json
GOOGLE_GMAIL_TOKEN_FILE=app/secrets/google/gmail_token.json
```

8. Starte Hammer Jarvis:

```powershell
.\scripts\start-jarvis.ps1
```

Beim ersten Gmail-Aufruf oeffnet sich der Browser fuer den lokalen OAuth-Login.
Das Token wird danach lokal unter `app/secrets/google/gmail_token.json` gespeichert und von Git ignoriert.

Der Status ist lokal abrufbar:

```text
GET http://127.0.0.1:8001/assistant/gmail/status
```

v0.4 nutzt nur den Gmail-Read-only-Scope `https://www.googleapis.com/auth/gmail.readonly`.
Gmail-Senden bleibt blockiert, und Gmail-Entwuerfe bleiben vorerst Mock-Verhalten.

## TimeTree limited / ICS

Hammer Jarvis nutzt keine direkte TimeTree-API, keine inoffizielle Scraping-Anbindung und keine TimeTree-Zugangsdaten.
TimeTree wird in v0.5 nur als lokale ICS-Lesequelle behandelt.

Lege die exportierte oder synchronisierte ICS-Datei lokal ab:

```text
app/data/timetree/timetree.ics
```

Aktiviere den Import in deiner lokalen `.env`:

```text
TIMETREE_ENABLED=true
TIMETREE_ICS_FILE=app/data/timetree/timetree.ics
```

Die lokalen TimeTree-Endpunkte sind:

```text
GET http://127.0.0.1:8001/assistant/timetree/status
GET http://127.0.0.1:8001/assistant/timetree/events
GET http://127.0.0.1:8001/assistant/timetree/today
```

TimeTree-Schreiben und das Erstellen von TimeTree-Terminen sind nicht unterstuetzt.
Speichere keine TimeTree-Benutzernamen, Passwoerter oder sonstigen Zugangsdaten in Hammer Jarvis.

## LLM Core / OpenAI

Hammer Jarvis v0.7 kann OpenAI als zentrale Orchestrierungsschicht verwenden.
Die OpenAI-Anbindung laeuft nur serverseitig im lokalen Backend.
Der API-Key wird nicht an den Browser gesendet.

Aktiviere die LLM-Anbindung in deiner lokalen `.env`:

```text
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.2
LLM_ENABLED=true
LLM_TOOL_MODE=true
LLM_MAX_TOOL_CALLS=5
```

Der Status ist lokal abrufbar:

```text
GET http://127.0.0.1:8001/assistant/llm/status
POST http://127.0.0.1:8001/assistant/llm/test
```

Hammer Jarvis laesst das LLM keine externen APIs direkt aufrufen.
Alle Aktionen laufen ueber die lokale Tool Registry und die bestehende Risiko-/Bestaetigungslogik.
Gruene Leseaktionen koennen direkt ausgefuehrt werden.
Gelbe Aktionen brauchen eine Bestaetigung.
Rote Aktionen wie E-Mail-Senden, PLC-Schreiben oder Dateien loeschen bleiben blockiert.

Ohne `OPENAI_API_KEY` oder mit `LLM_ENABLED=false` nutzt Hammer Jarvis den lokalen regelbasierten Fallback.

## Testen mit `/docs`

Oeffne `http://127.0.0.1:8001/docs` im Browser.
Dort kannst du die Endpunkte lokal testen.

Beispiel fuer `/chat`:

```json
{
  "message": "Welche Geraete sind nicht verfuegbar?"
}
```

Beispiel fuer bestaetigungspflichtiges Schalten:

```json
{
  "entity_id": "light.example",
  "confirm": true
}
```

Ohne `confirm: true` wird nicht geschaltet. Die API gibt stattdessen eine Bestaetigungsanforderung zurueck.

## Sicherheitskonzept Gruen/Gelb/Rot

- Gruen: Home Assistant Leseoperationen, zum Beispiel Status lesen, Entities suchen und unavailable Entities anzeigen.
- Gelb: Home Assistant Schreiboperationen, zum Beispiel `turn_on` und `turn_off`. Diese Aktionen brauchen eine ausdrueckliche Bestaetigung.
- Rot: PLC-Schreibzugriffe, Dateien loeschen, E-Mails senden und produktionsrelevante Aktionen. Diese Aktionen sind in v0.1 nicht implementiert.

Relevante Aktionen werden nach `app/logs/audit.log` geschrieben.
Tokens und andere Secrets duerfen nicht in Logs oder API-Antworten erscheinen.

## Bekannte Entities ignorieren

Bekannte optionale oder unwichtige Home Assistant Entities koennen in `app/config/entity_overrides.json` hinterlegt werden.
Das ist fuer Sensoren gedacht, die je nach Hardware optional sind und sonst unnoetig als kritisch erscheinen wuerden.

Beispiel:

```json
{
  "ignored_entities": [
    {
      "entity_id": "sensor.ecoflow_stream_ultra_x_0525_soc_ac_pro",
      "reason": "Optional AC Pro sensor. Ignore if no AC Pro extension is installed."
    }
  ],
  "downgraded_entities": []
}
```

Ignorierte EcoFlow-Entities erzeugen nur eine Info-Warnung und machen den Gesamtstatus nicht kritisch.
In diese Datei gehoeren keine Secrets.

## Persoenliche Prioritaetsregeln

Hammer Jarvis kann lokale Prioritaetsregeln fuer die Daily Briefings speichern.
Die Regeln liegen nur lokal in:

```text
app/config/personal_priority_rules.json
```

Es gibt Sender-Regeln und Betreff-Regeln. Sie beeinflussen nur die Jarvis-Analyse, nicht Gmail selbst.
Jarvis sendet, loescht oder veraendert dadurch keine E-Mails und fuehrt kein Auto-Unsubscribe aus.

Beispiele fuer Feedback-Kommandos:

```text
Jarvis, LOTTO24 ist unwichtig.
Jarvis, Dreame ist Werbung.
Jarvis, LinkedIn Jobs sind mittel wichtig.
Jarvis, Fernakademie ist wichtig.
Jarvis, GitHub Sicherheitsmails sind wichtig.
Jarvis, merke dir, dass Absender Beispiel unwichtig ist.
Jarvis, priorisiere Absender Beispiel hoch.
```

Die Regeln sind lokal abrufbar und bearbeitbar:

```text
GET http://127.0.0.1:8001/assistant/priority/personal-rules
POST http://127.0.0.1:8001/assistant/priority/personal-rules/sender
POST http://127.0.0.1:8001/assistant/priority/personal-rules/subject
DELETE http://127.0.0.1:8001/assistant/priority/personal-rules
```

## Dateien erstellen

Hammer Jarvis kann lokale Excel-, CSV-, Markdown- und JSON-Dateien erstellen.
Alle generierten Dateien werden im lokalen Exportordner abgelegt:

```text
workspace/exports
```

Der Exportordner ist fuer lokale Arbeitsdateien gedacht. Er wird nicht in Git committed.
Hammer Jarvis ueberschreibt bestehende Dateien nicht automatisch, sondern erzeugt bei Namenskonflikten einen neuen Dateinamen mit Suffix wie `_001`.
Dateien werden nicht geloescht, und Pfade ausserhalb des Exportordners werden abgelehnt.

Lokale Endpunkte:

```text
POST http://127.0.0.1:8001/assistant/files/create/excel
POST http://127.0.0.1:8001/assistant/files/create/csv
POST http://127.0.0.1:8001/assistant/files/create/markdown
POST http://127.0.0.1:8001/assistant/files/create/json
GET http://127.0.0.1:8001/assistant/files/exports
```

Beispiele fuer Sprach- oder Chatbefehle:

```text
Erstelle eine Excel fuer Ausgaben.
Erstelle eine Vorlage Wartungsplan.
Exportiere EcoFlow Tageswerte als Excel.
```

## Dateien suchen und oeffnen

Hammer Jarvis kann lokale Dateien nur in explizit erlaubten Verzeichnissen suchen und oeffnen.
Konfiguriere die erlaubten Ordner in deiner lokalen `.env`:

```text
FILE_SEARCH_ENABLED=true
FILE_SEARCH_ALLOWED_DIRS=workspace/exports;C:/Users/alwin/OneDrive;C:/Users/alwin/Documents
FILE_SEARCH_MAX_RESULTS=25
```

OneDrive kann ueber den lokal synchronisierten Ordner eingebunden werden.
Jarvis durchsucht nicht automatisch das gesamte Laufwerk `C:\`.
Dateien werden mit der Windows-Standardanwendung geoeffnet.
Loeschen, Verschieben und Veraendern von Dateien ist nicht implementiert.
Dateien ausserhalb der erlaubten Verzeichnisse werden blockiert.

Lokale Endpunkte:

```text
GET http://127.0.0.1:8001/assistant/files/search?q=ausgaben&extension=.xlsx
GET http://127.0.0.1:8001/assistant/files/recent
POST http://127.0.0.1:8001/assistant/files/open
POST http://127.0.0.1:8001/assistant/files/open-latest
```

Beispiele fuer Sprach- oder Chatbefehle:

```text
Finde die Excel mit meinen Ausgaben.
Oeffne die letzte erstellte Datei.
Oeffne ausgaben.xlsx.
```

## Dateiinhalte durchsuchen

Hammer Jarvis kann Inhalte lokaler Dateien in erlaubten Ordnern durchsuchen.
Die Suche bleibt lokal und nutzt nur die in `FILE_SEARCH_ALLOWED_DIRS` konfigurierten Verzeichnisse.
Es werden keine Inhalte hochgeladen, keine Dateien veraendert und keine Dateien geloescht.

Unterstuetzte Formate:

- PDF
- DOCX
- XLSX / XLSM
- CSV
- TXT
- MD
- JSON

Grosse Dateien koennen uebersprungen werden. Standardlimit:

```text
FILE_CONTENT_MAX_FILE_SIZE_MB=25
```

Scans oder bildbasierte PDFs werden noch nicht per OCR gelesen.
Fuer solche Dateien braucht Hammer Jarvis spaeter eine separate lokale OCR-Funktion.

Lokale Endpunkte:

```text
GET http://127.0.0.1:8001/assistant/files/content-search?q=Kaufvertrag&extension=.pdf
POST http://127.0.0.1:8001/assistant/files/inspect
```

Beispiele:

```text
Suche in PDFs nach Kaufvertrag.
Welche PDF enthaelt Energieausweis?
Suche in Dokumenten nach Rechnungsnummer 12345.
```

## Dateien inspizieren und zusammenfassen

Hammer Jarvis kann gefundene lokale Dateien inspizieren, den besten Treffer oeffnen,
Dokumente zusammenfassen und einfache Eckdaten extrahieren.
Das funktioniert nur fuer Dateien innerhalb der erlaubten Ordner aus `FILE_SEARCH_ALLOWED_DIRS`.

Die Zusammenfassung nutzt, wenn verfuegbar, das lokale Ollama-LLM.
Dateiinhalte werden nicht an externe APIs hochgeladen.
Wenn kein lokales LLM verfuegbar ist, zeigt Jarvis stattdessen extrahierte Textauszuege.
Dateien werden nicht veraendert, nicht geloescht und nicht verschoben.

Fuer Kaufvertraege sucht Jarvis deterministisch nach Begriffen wie:

- Kaufpreis
- Kaeufer / Verkaeufer
- Objekt / Adresse
- Grundbuch
- Notar
- UVZ
- Faelligkeit / Fristen
- Besitzuebergang
- Auflassung
- Grundschuld

OCR fuer gescannte PDFs ist noch nicht enthalten.

Lokale Endpunkte:

```text
GET http://127.0.0.1:8001/assistant/files/last-results
POST http://127.0.0.1:8001/assistant/files/inspect
POST http://127.0.0.1:8001/assistant/files/summarize
POST http://127.0.0.1:8001/assistant/files/extract-key-fields
POST http://127.0.0.1:8001/assistant/files/open-best-match
POST http://127.0.0.1:8001/assistant/files/open-result
```

Beispiele:

```text
Oeffne den besten Treffer.
Oeffne Treffer 1.
Fasse den Kaufvertrag zusammen.
Extrahiere die wichtigsten Daten aus dem Kaufvertrag.
```

## Internetrecherche

Hammer Jarvis kann Webrecherche ueber eine lokale SearXNG-Instanz ausfuehren.
Die Funktion ist standardmaessig deaktiviert und muss in der lokalen `.env` aktiviert werden:

```text
WEB_RESEARCH_ENABLED=true
WEB_SEARCH_PROVIDER=searxng
SEARXNG_BASE_URL=http://localhost:8080
WEB_SEARCH_MAX_RESULTS=5
WEB_FETCH_TIMEOUT_SECONDS=15
```

Jarvis beantwortet Recherchefragen nur mit Suchergebnissen und Quellen.
Wenn die Websuche nicht konfiguriert oder SearXNG nicht erreichbar ist, gibt Jarvis eine klare Fehlermeldung zurueck.
Es werden keine Dateien von Webseiten heruntergeladen und kein Code von Webseiten ausgefuehrt.

Lokale Endpunkte:

```text
GET http://127.0.0.1:8001/assistant/web/status
GET http://127.0.0.1:8001/assistant/web/search?q=Microsoft%20Graph
POST http://127.0.0.1:8001/assistant/web/research
```

Beispiele:

```text
Recherchiere offizielle Dokumentation zu Microsoft Graph Search.
Suche im Internet nach aktuellen Informationen zu Python 3.11.
Pruefe im Internet, welche Dokumentation Microsoft zu OneDrive Search bereitstellt.
```

## Nuetzliche Skills

Hammer Jarvis v1.5 enthaelt einen lokalen Skills-Layer fuer haeufige Arbeitsablaeufe.
Skills kombinieren vorhandene sichere Werkzeuge wie Dateisuche, Inhaltsextraktion,
Webrecherche und Datei-Export. Alle lokalen Dokumente bleiben lokal; Dateiinhalte
werden nicht extern hochgeladen.

Unterstuetzte Skills:

- Lokale Dokumente zusammenfassen
- Eckdaten aus Dokumenten extrahieren, zum Beispiel aus Kaufvertraegen
- Suchberichte als Markdown erstellen
- Dokumentenindizes als Excel erstellen
- Webrecherche-Berichte mit Quellen als Markdown erstellen
- Webquellen als Excel-Liste exportieren

Alle erzeugten Dateien werden unter `workspace/exports` gespeichert.
Bestehende Dateien werden nicht ueberschrieben; Hammer Jarvis erzeugt bei Bedarf
einen neuen Dateinamen mit Suffix. Dateien werden nicht geloescht, nicht verschoben
und OneDrive-Dateien werden nicht veraendert.

Hammer Jarvis durchsucht und liest nur Ordner, die in `FILE_SEARCH_ALLOWED_DIRS`
konfiguriert sind. Wenn das lokale Ollama-LLM nicht erreichbar ist, nutzt die
Dokumentzusammenfassung deterministische Textauszuege statt erfundener Inhalte.

Lokale Endpunkte:

```text
GET http://127.0.0.1:8001/assistant/skills
POST http://127.0.0.1:8001/assistant/skills/document/summarize
POST http://127.0.0.1:8001/assistant/skills/document/extract-key-fields
POST http://127.0.0.1:8001/assistant/skills/files/search-report
POST http://127.0.0.1:8001/assistant/skills/files/index-excel
POST http://127.0.0.1:8001/assistant/skills/web/report
POST http://127.0.0.1:8001/assistant/skills/web/excel
```

Beispiele:

```text
Fasse den besten Treffer zusammen.
Extrahiere die wichtigsten Daten aus dem Kaufvertrag.
Erstelle mir einen Bericht ueber alle Hauskauf-PDFs.
Erstelle eine Excel-Uebersicht der Hauskauf-Dokumente.
Recherchiere Foerderungen fuer PV in Bayern und erstelle eine Excel mit Quellen.
```

## Sichere Aktionen und Bestaetigungen

Hammer Jarvis v1.6 kann aus Diagnose- und Suchergebnissen sichere naechste
Aktionen vorschlagen. Diese Aktionen werden zunaechst lokal als ausstehende
Aktionen gespeichert und koennen im Dashboard oder per Chat ausgefuehrt oder
abgelehnt werden.

Sicherheitsregeln:

- Gruene Aktionen sind lese- oder exportorientiert und koennen direkt ausgefuehrt werden.
- Gelbe Aktionen brauchen eine ausdrueckliche Bestaetigung.
- Rote Aktionen sind blockiert.
- Home-Assistant-Schaltaktionen werden nie ohne Bestaetigung ausgefuehrt.
- Dateien werden nicht geloescht.
- E-Mails werden nicht gesendet.
- Gmail und OneDrive-Dateien werden nicht veraendert.
- SPS-/PLC-Schreibzugriffe sind blockiert.
- Alle Ausfuehrungen laufen ueber die lokale Tool Registry und werden im Audit-Log protokolliert.

Ausstehende Aktionen laufen standardmaessig nach kurzer Zeit ab.
Die aktuelle In-Memory-Aktionsliste wird nicht dauerhaft gespeichert.

Lokale Endpunkte:

```text
GET http://127.0.0.1:8001/assistant/actions/pending
POST http://127.0.0.1:8001/assistant/actions/{action_id}/execute
POST http://127.0.0.1:8001/assistant/actions/{action_id}/reject
DELETE http://127.0.0.1:8001/assistant/actions/expired
```

Beispiele:

```text
Was schlaegst du vor?
Welche Aktionen stehen aus?
Fuehre Aktion 1 aus.
Bestaetige Aktion 1.
Aktion 1 ablehnen.
```

## Tests

```powershell
python -m pytest
```

Die Tests verwenden keinen echten Home Assistant Server.

## Aktuelle Einschraenkungen v0.1

- Kein Frontend
- Kein Docker
- Keine Datenbank
- Keine Python-Audiofunktionen, kein Wake Word und kein Always-Listening-Modus
- Keine PLC-Verbindung
- Keine autonomen Aktionen
- Kein Cloud-Deployment
- Keine OpenAI API Calls
- Kein LangChain
