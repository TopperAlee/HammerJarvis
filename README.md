# Hammer Jarvis

Hammer Jarvis ist ein lokaler, Windows-first Backend-Prototyp fuer einen persoenlichen AI-Assistenten.
Version 0.1 verbindet sich mit Home Assistant ueber die REST API und stellt lokale FastAPI-Endpunkte bereit.

## Zweck des Projekts

Das Projekt soll lokale Assistant-Funktionen bereitstellen, ohne Cloud-Deployment, Docker, Datenbank, Voice-Control oder autonome Aktionen.
In v0.1 gibt es einfache regelbasierte Chat-Kommandos und Home-Assistant-Werkzeuge fuer Statusabfragen, Suche, Energie-/Leistungswerte und bestaetigungspflichtiges Schalten.

## Projekt-Dokumentation

- [Vision](VISION.md)
- [Changelog](CHANGELOG.md)
- [Architektur](docs/architecture/README.md)
- [Roadmap](docs/roadmap/README.md)

Der ProTool Assistant ist das erste read-only Engineering-Modul von HammerJarvis. Er analysiert ProTool-CSV-Dateien, erstellt Reports und Panel-Vorschauen, veraendert aber keine CSV- oder Projektdateien.

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

### Sprachausgabe

Hammer Jarvis verwendet aktuell die Browser-Web-Speech-API fuer die lokale
Sprachausgabe im Dashboard. Die tatsaechliche Sprachqualitaet haengt von den
auf Windows und im verwendeten Browser verfuegbaren Stimmen ab.

Im Dashboard kann eine verfuegbare deutsche Stimme ausgewaehlt werden. Die
Auswahl wird lokal im Browser per `localStorage` gespeichert und beim naechsten
Oeffnen wiederhergestellt, sofern die Stimme weiterhin verfuegbar ist.

Es werden keine Sprachdaten an einen neu eingebauten externen TTS-Dienst
uebertragen. Browser-TTS ist weiterhin eine Zwischenloesung und keine neuronale
Jarvis-Stimme.

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

## LLM Core / lokal und optional OpenAI

Hammer Jarvis kann lokale LLMs ueber Ollama oder optional OpenAI als
Orchestrierungsschicht verwenden. Bekannte lokale Domaenen wie EcoFlow,
Home Assistant, Gmail, TimeTree und Dateien laufen zuerst ueber echte Tools.
Das LLM formatiert oder ergaenzt Antworten nur dort, wo es sicher passt.

Lokaler Ollama-Betrieb:

```text
LLM_ENABLED=true
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3:8b
OLLAMA_MODEL_FAST=llama3.2:3b
OLLAMA_MODEL_SMART=qwen3:8b
OLLAMA_API_KEY=ollama
LLM_TOOL_MODE=true
LLM_COMPLEXITY_ROUTING=false
OLLAMA_KEEP_ALIVE=30m
OLLAMA_USE_NATIVE_API=false
OLLAMA_WARMUP_ENABLED=true
OLLAMA_WARMUP_ON_STARTUP=true
```

Ollama entscheidet selbst, ob CPU oder GPU verwendet wird. Wenn eine passende
GPU verfuegbar ist und das Modell hineinpasst, nutzt Ollama sie automatisch.
Fuer schnelle Alltagsantworten kann ein kleineres Modell wie `llama3.2:3b`
als Fast-Modell konfiguriert werden; `qwen3:8b` bleibt als staerkeres
Standardmodell geeignet.

Lokale Status- und Diagnose-Endpunkte:

```text
GET http://127.0.0.1:8001/assistant/llm/status
GET http://127.0.0.1:8001/assistant/ollama/status
GET http://127.0.0.1:8001/assistant/ollama/benchmark
GET http://127.0.0.1:8001/assistant/ollama/benchmark/native
GET http://127.0.0.1:8001/assistant/ollama/benchmark/warm
POST http://127.0.0.1:8001/assistant/llm/test
```

`/assistant/ollama/status` zeigt, ob Ollama erreichbar ist, welche Modelle
installiert sind und ob das konfigurierte Modell gefunden wurde.
`/assistant/ollama/benchmark` fuehrt einen kurzen lokalen Antworttest aus und
liefert die gemessene Antwortzeit in Millisekunden.

Optionale OpenAI-Anbindung:

```text
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.2
LLM_ENABLED=true
LLM_PROVIDER=openai
LLM_TOOL_MODE=true
LLM_MAX_TOOL_CALLS=5
```

Hammer Jarvis laesst das LLM keine externen APIs direkt aufrufen.
Alle Aktionen laufen ueber die lokale Tool Registry und die bestehende Risiko-/Bestaetigungslogik.
Gruene Leseaktionen koennen direkt ausgefuehrt werden.
Gelbe Aktionen brauchen eine Bestaetigung.
Rote Aktionen wie E-Mail-Senden, PLC-Schreiben oder Dateien loeschen bleiben blockiert.

Mit `LLM_PROVIDER=none` oder `LLM_ENABLED=false` nutzt Hammer Jarvis den
lokalen regelbasierten Fallback.

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
FILE_CONTENT_CACHE_ENABLED=true
FILE_CONTENT_CACHE_MAX_ITEMS=200
```

Die Inhaltsextraktion nutzt optional einen kleinen In-Memory-Cache fuer
unveraenderte Dateien. Der Cache speichert nur extrahierten Text aus lokalen
erlaubten Ordnern, keine Binaerdaten und keine Dateien ausserhalb der
konfigurierten Suchpfade.

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

## Lokales Projektwissen

Hammer Jarvis kann Dokumente als lokales Projektwissen aufnehmen und fuer
normale Assistant-Fragen als begrenzten Kontext verwenden. Der Speicher ist
lokal: Standardmaessig liegen Index und verwaltete Uploads unter
`%LOCALAPPDATA%\HammerJarvis\knowledge`. Es werden keine Dokumente in eine
Cloud hochgeladen und keine Vektordatenbank verwendet.

Unterstuetzte Uploadformate sind PDF, DOCX, XLSX, XLSM, CSV, TXT, Markdown und
JSON. Die Standardgrenze pro Upload betraegt 25 MB und kann ueber
`KNOWLEDGE_MAX_UPLOAD_MB` in der lokalen `.env` angepasst werden. XLSM-Dateien
werden ausschliesslich lesend verarbeitet; Makros werden nicht ausgefuehrt.
Bildbasierte oder textlose PDFs erhalten den Status `OCR erforderlich`; OCR ist
in dieser Version nicht enthalten.

Im Dashboard unter **Projektwissen** koennen Dateien per Drag-and-drop oder
Dateiauswahl hochgeladen werden. Die Dokumentliste zeigt nur Metadaten und
begrenzte Vorschauen. Uploads lassen sich neu indexieren oder entfernen. Beim
Entfernen eines Uploads wird nur die verwaltete Kopie entfernt; beim Entfernen
eines ueber einen lokalen Pfad indexierten Dokuments bleibt die Originaldatei
erhalten.

Bestehende lokale Pfadindexierung bleibt moeglich und wird nur fuer die in
`KNOWLEDGE_ALLOWED_DIRS` erlaubten Ordner akzeptiert. Dokumentnamen, Pfade und
Inhalte werden validiert; `.env`, Secrets-Verzeichnisse und Dateien ausserhalb
der erlaubten Ordner werden nicht indexiert.

Wenn eine normale Assistant-Frage passende Dokumenttreffer hat, erhaelt das
lokale LLM einen begrenzten, als untrusted markierten Dokumentkontext. Lokale
Pfade gelangen nicht in den LLM-Prompt. Quellen erscheinen ausschliesslich
unter der jeweiligen Chatantwort, werden nicht als Teil der Antwort vorgelesen
und enthalten keine SHA-256-Werte, gespeicherten Dateinamen oder Chunk-IDs.

Lokale Knowledge-Endpunkte:

```text
GET    http://127.0.0.1:8001/assistant/knowledge/status
POST   http://127.0.0.1:8001/assistant/knowledge/index
GET    http://127.0.0.1:8001/assistant/knowledge/search?q=Kaufvertrag
GET    http://127.0.0.1:8001/assistant/knowledge/documents
POST   http://127.0.0.1:8001/assistant/knowledge/upload
GET    http://127.0.0.1:8001/assistant/knowledge/documents/{document_id}
POST   http://127.0.0.1:8001/assistant/knowledge/documents/{document_id}/reindex
DELETE http://127.0.0.1:8001/assistant/knowledge/documents/{document_id}
```

Manuelle Windows-PowerShell-Pruefung:

```powershell
.\scripts\start-jarvis.ps1
Start-Process http://127.0.0.1:8001/dashboard
```

Danach eine harmlose lokale Testdatei hochladen, die Quellenanzeige einer
passenden Chatantwort pruefen und die vollstaendige Checkliste in
`docs\knowledge-dashboard-manual-check.md` verwenden.

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

## Sichere Smart-Home-Aktionen

Hammer Jarvis v1.7 kann begrenzte Home-Assistant-Aktionen vorbereiten. Aktionen
sind standardmaessig gesperrt und muessen explizit in dieser Datei freigegeben
werden:

```text
app/config/home_assistant_action_allowlist.json
```

Unterstuetzt werden zunaechst nur:

- `light.turn_on`
- `light.turn_off`
- `switch.turn_on`
- `switch.turn_off`
- `scene.turn_on`

Jede Ausfuehrung ist eine gelbe Aktion und braucht eine ausdrueckliche
Bestaetigung, zum Beispiel:

```text
Schalte Wohnzimmer Licht ein.
Bestaetige Aktion 1.
```

Gefaehrliche oder sicherheitskritische Domaenen bleiben blockiert. Dazu gehoeren
unter anderem Locks, Alarmanlagen, Heizung/Thermostate, Garagentore, Oefen,
Pumpen, Kameras und industrielle Steuerungen. Hammer Jarvis akzeptiert keine
frei eingegebenen Home-Assistant-Servicenamen.

Beispiel-Allowlist:

```json
{
  "allowed_entities": [
    {
      "entity_id": "light.wohnzimmer",
      "friendly_name": "Wohnzimmer Licht",
      "domain": "light",
      "allowed_actions": ["turn_on", "turn_off"]
    }
  ],
  "allowed_scenes": [],
  "blocked_domains": ["lock", "alarm_control_panel", "cover", "climate"]
}
```

Lokaler Status:

```text
GET http://127.0.0.1:8001/assistant/home-assistant/actions/allowed
```

## Home Assistant Entity Catalog

Hammer Jarvis kann alle Home-Assistant-Entities regelmaessig read-only abrufen
und lokal als sicheren Entity-Katalog zwischenspeichern. Der Katalog ist fuer
Suche, Diagnose, Discovery und Freigabe-Vorschlaege gedacht.

Wichtig: Der Katalog gibt keine Schaltrechte. Nur weil Jarvis eine Entity kennt,
darf er sie nicht automatisch steuern. Schalten bleibt weiterhin:

1. erlaubte Domain
2. Eintrag in `app/config/home_assistant_action_allowlist.json`
3. gelbe Aktion mit ausdruecklicher Bestaetigung

Konfiguration in `.env`:

```text
HA_ENTITY_SYNC_ENABLED=true
HA_ENTITY_SYNC_INTERVAL_SECONDS=300
HA_ENTITY_CACHE_FILE=app/data/home_assistant/entities_cache.json
HA_ENTITY_CACHE_MAX_AGE_SECONDS=900
```

Der Cache liegt lokal unter `app/data/home_assistant/` und wird nicht committed.
Gespeichert werden nur sichere Metadaten wie Entity-ID, Domain, Status,
Friendly Name, Zeitstempel und eine kleine Attribut-Zusammenfassung. Vollstaendige
Attribute werden nicht blind gespeichert.

Lokale Endpunkte:

```text
GET  http://127.0.0.1:8001/assistant/home-assistant/entities/status
POST http://127.0.0.1:8001/assistant/home-assistant/entities/sync
GET  http://127.0.0.1:8001/assistant/home-assistant/entities
GET  http://127.0.0.1:8001/assistant/home-assistant/entities/search?q=flur
GET  http://127.0.0.1:8001/assistant/home-assistant/entities/unavailable
GET  http://127.0.0.1:8001/assistant/home-assistant/entities/actionable-candidates
GET  http://127.0.0.1:8001/assistant/home-assistant/entities/light.wohnzimmer
```

Beispiele:

```text
Synchronisiere Home Assistant Entities.
Zeige alle Lichter.
Suche Flur in Home Assistant.
Welche Geraete kann ich freigeben?
Zeige Details zu switch.hall.
```

Switches werden nur als moegliche Kandidaten angezeigt. Sie koennen Steckdosen
oder echte Verbraucher sein und sollten nur freigegeben werden, wenn eindeutig
klar ist, dass die Aktion ungefaehrlich ist.

## Universal Home Assistant Control Broker

Hammer Jarvis v2.0 besitzt einen Universal Control Broker fuer Home Assistant.
Der Broker ist bewusst kein freier Service-Call-Proxy. Jarvis darf Entities
kennen und Steueraktionen vorbereiten, aber jede Ausfuehrung laeuft durch:

1. feste Domain-/Action-Mappings
2. lokale Control Policy
3. ToolRegistry und Permission Layer
4. ausstehende Aktion mit Bestaetigung
5. Audit Log

Es gibt keine beliebigen Home-Assistant-Servicenamen aus dem LLM und keine frei
gebauten Service-Payloads aus Benutzereingaben. Hochriskante Geraete bleiben
standardmaessig blockiert.

Policy-Datei:

```text
app/config/home_assistant_control_policy.json
```

Beispiel fuer einen Entity-Override:

```json
{
  "entity_overrides": {
    "switch.hall": {
      "enabled": true,
      "risk": "YELLOW",
      "friendly_name": "Flur Licht",
      "allowed_actions": ["turn_on", "turn_off"]
    }
  }
}
```

Unterstuetzte Mappings:

- `light`: `turn_on`, `turn_off`, `toggle`
- `switch`: `turn_on`, `turn_off`, `toggle`
- `scene`: `turn_on`
- `script`: `turn_on`
- `automation`: `turn_on`, `turn_off`
- `cover`: `open_cover`, `close_cover`, `stop_cover`
- `climate`: `set_temperature`

Risk-Stufen:

- GELB: normale Geraetesteuerung, Bestaetigung erforderlich
- ORANGE: erhoehte Vorsicht, Bestaetigung und Warnhinweis erforderlich
- ROT: blockiert, PIN-Infrastruktur ist vorbereitet, aber standardmaessig nicht aktiv

Batch-Aktionen sind begrenzt:

```text
HA_CONTROL_MAX_BATCH_SIZE=20
```

Lokale Endpunkte:

```text
GET  http://127.0.0.1:8001/assistant/home-assistant/control/policy
GET  http://127.0.0.1:8001/assistant/home-assistant/control/entities
POST http://127.0.0.1:8001/assistant/home-assistant/control/resolve
POST http://127.0.0.1:8001/assistant/home-assistant/control/prepare
POST http://127.0.0.1:8001/assistant/home-assistant/control/execute
POST http://127.0.0.1:8001/assistant/home-assistant/control/batch/prepare
POST http://127.0.0.1:8001/assistant/home-assistant/control/batch/execute
```

Beispiele:

```text
Flur Licht einschalten.
Alle Lichter aus.
Temperatur auf 21 Grad.
Rollladen schließen.
```

Diese Befehle erstellen nur ausstehende Aktionen. Ausfuehrung erfolgt erst nach:

```text
Bestaetige Aktion 1.
```

## Lokales Gedächtnis

Hammer Jarvis v2.1 kann explizit freigegebene Fakten, Präferenzen,
Korrekturen, Projektwissen und Gerätezusammenhänge lokal speichern.
Das Gedächtnis liegt als UTF-8-JSON-Datei auf diesem Rechner:

```text
MEMORY_ENABLED=true
MEMORY_FILE=app/data/memory/memory.json
MEMORY_REQUIRE_CONFIRMATION_FOR_SENSITIVE=true
MEMORY_MAX_ITEMS=1000
```

Jarvis speichert nicht automatisch alles, was gesagt wird. Speicherbefehle
müssen ausdrücklich sein, zum Beispiel:

```text
Merke dir, dass switch.hall das Flurlicht ist.
Speichere, dass LOTTO24 unwichtig ist.
Für die Zukunft: Projekt X nutzt lokale Tools.
Was weißt du über switch.hall?
Vergiss switch.hall.
```

Nicht gespeichert werden dürfen:

- Passwörter
- API Keys
- OAuth- oder Bearer Tokens
- Bank-Logins
- vollständige private Dokumente
- sicherheitskritische Geheimnisse

Solche Inhalte werden blockiert. Sensible Erinnerungen können später über
bestätigungspflichtige Aktionen behandelt werden. Gedächtnisinhalte können
gelistet, gesucht, bearbeitet, gelöscht und exportiert werden.

Lokale Endpunkte:

```text
GET    http://127.0.0.1:8001/assistant/memory/status
GET    http://127.0.0.1:8001/assistant/memory
GET    http://127.0.0.1:8001/assistant/memory/search?q=switch.hall
POST   http://127.0.0.1:8001/assistant/memory
PATCH  http://127.0.0.1:8001/assistant/memory/{id}
DELETE http://127.0.0.1:8001/assistant/memory/{id}
POST   http://127.0.0.1:8001/assistant/memory/export
```

Memory-Kontext kann bei freien LLM-Antworten als kurzer lokaler Kontext
eingeblendet werden. Tool-first-Routing bleibt vorrangig. Gedächtnis kann keine
Smart-Home-Schaltrechte vergeben und umgeht weder Control Policy noch
Bestätigungen.

## Performance Check

Hammer Jarvis sammelt einfache lokale In-Memory-Metriken fuer wichtige
Operationen. Es werden nur Operationsname, Kategorie, Dauer, Erfolg/Fehler und
Zeitstempel gespeichert. Prompts, Tokens, Dateiinhalte, OAuth-Daten und Secrets
werden nicht in Performance-Metriken geschrieben.

Konfiguration:

```text
PERFORMANCE_METRICS_ENABLED=true
PERFORMANCE_METRICS_MAX_ITEMS=500
```

Lokale Endpunkte:

```text
GET http://127.0.0.1:8001/assistant/performance/status
GET http://127.0.0.1:8001/assistant/performance/benchmark
GET http://127.0.0.1:8001/assistant/ollama/benchmark
GET http://127.0.0.1:8001/assistant/ollama/benchmark/models
GET http://127.0.0.1:8001/assistant/ollama/benchmark/native
GET http://127.0.0.1:8001/assistant/ollama/benchmark/warm
GET http://127.0.0.1:8001/assistant/ollama/performance-advice
```

`/assistant/performance/status` zeigt die letzten und langsamsten lokalen
Operationen. `/assistant/performance/benchmark` fuehrt kleine sichere Checks
aus: Entity-Cache-Status, kleine Dateisuche in den erlaubten Ordnern,
Dashboard-Dateicheck, Memory-Suche und optional einen kleinen Ollama-Test.

Native Ollama-Benchmarks geben keine raw `context`-Arrays aus. Sie zeigen nur
kompakte Felder wie `measured_http_duration_ms`, `measured_total_duration_ms`,
`ollama_total_duration_ms`, `load_duration_ms`, `eval_duration_ms`,
`output_length`, `warning` und `cold_start_likely`.

Native Benchmark-Auswahl:

```text
GET /assistant/ollama/benchmark/native?models=current
GET /assistant/ollama/benchmark/native?models=fast
GET /assistant/ollama/benchmark/native?models=smart
GET /assistant/ollama/benchmark/native?models=all
GET /assistant/ollama/benchmark/warm
GET /assistant/ollama/benchmark/warm?model=qwen3:8b
```

`models=current` ist der Standard. Der Warm-Benchmark nutzt standardmaessig
`OLLAMA_MODEL_FAST`, falls installiert, sonst `OLLAMA_MODEL`, und misst nur
dieses eine Modell zweimal.

Ollama/GPU-Hinweis: Hammer Jarvis erkennt hier nicht selbst, ob die GPU aktiv
ist. Ollama entscheidet lokal anhand Installation, Treibern und Modell. Der
Benchmark misst nur Antwortzeit und Antwortlaenge.

Relevante Performance-Grenzen:

```text
HOME_ASSISTANT_TIMEOUT_SECONDS=10
HA_ENTITY_SYNC_INTERVAL_SECONDS=300
HA_ENTITY_SYNC_MIN_INTERVAL_SECONDS=30
HA_ENTITY_CACHE_MAX_AGE_SECONDS=900

FILE_SEARCH_MAX_RESULTS=25
FILE_SEARCH_MAX_DEPTH=12
FILE_SEARCH_TIMEOUT_SECONDS=20
FILE_CONTENT_MAX_FILE_SIZE_MB=25
FILE_CONTENT_CACHE_ENABLED=true
FILE_CONTENT_CACHE_MAX_ITEMS=200
FILE_CONTENT_PREVIEW_CHARS=4000

WEB_SEARCH_CACHE_ENABLED=true
WEB_SEARCH_CACHE_TTL_SECONDS=300
WEB_FETCH_MAX_BYTES=500000
WEB_FETCH_TIMEOUT_SECONDS=15

OLLAMA_MODEL_FAST=llama3.2:3b
OLLAMA_MODEL_SMART=qwen3:8b
LLM_COMPLEXITY_ROUTING=false
OLLAMA_KEEP_ALIVE=30m
OLLAMA_HTTP_TIMEOUT_SECONDS=60
OLLAMA_BENCHMARK_NUM_PREDICT=2
OLLAMA_BENCHMARK_NUM_CTX=512
OLLAMA_USE_NATIVE_API=false
OLLAMA_WARMUP_ENABLED=true
OLLAMA_WARMUP_ON_STARTUP=true

LLM_MAX_PROMPT_MEMORY_ITEMS=8
LLM_MAX_CONTEXT_CHARS=12000
```

Dateisuche: OneDrive- und Dokumentenordner koennen gross sein. Hammer Jarvis
ueberspringt schwere Ordner wie `.git`, `.venv`, `node_modules`, `__pycache__`
und versteckte Ordner. Fuer genauere PDF-Suchen sollte die Inhaltssuche mit
konkreten Begriffen genutzt werden. Beschädigte PDFs oder OneDrive-Platzhalter
werden strukturiert uebersprungen.

Home Assistant: Der Entity Catalog vermeidet wiederholte vollständige
`/api/states`-Abrufe. Force-Sync sollte nur bewusst genutzt werden.

Dashboard: Die HUD-Daten werden periodisch aktualisiert. Entity Catalog und
Control Broker sollten bevorzugt manuell oder mit laengeren Intervallen
aktualisiert werden, wenn Home Assistant oder OneDrive langsam reagieren.

Troubleshooting:

- Langsames Ollama: kleineres Modell als `OLLAMA_MODEL_FAST` testen.
- Langsame OneDrive-Suche: erlaubte Ordner enger setzen und `FILE_SEARCH_MAX_DEPTH` reduzieren.
- Langsame PDF-Suche: `FILE_CONTENT_MAX_FILE_SIZE_MB` reduzieren oder gezieltere Begriffe verwenden.
- Langsame Webrecherche: SearXNG pruefen und `WEB_SEARCH_MAX_RESULTS` niedrig halten.

HA Sync: Parallele Entity-Synchronisationen werden zusammengefuehrt. Wenn
innerhalb von `HA_ENTITY_SYNC_MIN_INTERVAL_SECONDS` bereits ein Live-Sync
gelaufen ist, nutzt Jarvis bei `force=false` den aktuellen Cache und startet
keinen zweiten `/api/states`-Abruf.

## Ollama Performance und GPU

Hammer Jarvis fuehrt das Modell nicht direkt aus. Die lokale Ollama-Installation
entscheidet selbst, ob CPU oder GPU genutzt wird. Hammer Jarvis behauptet daher
nicht, dass GPU-Beschleunigung aktiv ist, solange sie nicht extern beobachtet
wurde.

Pruefen kannst du die Antwortzeit so:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/assistant/ollama/benchmark
Invoke-RestMethod http://127.0.0.1:8001/assistant/ollama/benchmark/models
Invoke-RestMethod http://127.0.0.1:8001/assistant/ollama/performance-advice
```

Oeffne parallel den Windows Task-Manager und beobachte CPU/GPU-Last. Bei NVIDIA
kann optional `nvidia-smi` helfen, falls es installiert ist.

Empfohlene lokale Modellaufteilung:

```text
OLLAMA_MODEL_FAST=llama3.2:3b
OLLAMA_MODEL_SMART=qwen3:8b
LLM_COMPLEXITY_ROUTING=false
```

`LLM_COMPLEXITY_ROUTING=false` bleibt der Standard. Wenn du es aktivierst,
koennen einfache nicht-deterministische Antworten ein kleineres Fast-Modell
nutzen. Werkzeugbefehle wie Hauscheck, EcoFlow, Dateisuche, Web-Recherche und
Smart-Home-Freigaben umgehen das LLM weiterhin deterministisch.

Wenn `/assistant/ollama/benchmark/warm` zeigt, dass der warme native Lauf
schnell ist, aber der OpenAI-kompatible Benchmark langsam bleibt, kann
`OLLAMA_USE_NATIVE_API=true` sinnvoll sein. Die native API sendet `keep_alive`
an Ollama und reduziert Overhead fuer einfache lokale Chatantworten. Werkzeug-
und Sicherheitsrouting bleiben unveraendert.

## Smart-Home-Freigaben verwalten

Hammer Jarvis kann sichere Home-Assistant-Kandidaten anzeigen und daraus
Freigabe-Aktionen vorbereiten. Dabei wird nichts geschaltet und nichts
automatisch freigegeben.

Regeln:

- Kandidaten werden nur aus `light`, `switch` und `scene` gebildet.
- Locks, Alarmanlagen, Heizung/Klima, Garagen/Tueren, Pumpen, Kameras und
  andere kritische Domaenen bleiben blockiert.
- Hinzufuegen und Entfernen aus der Freigabe sind gelbe Aktionen und brauchen
  Bestaetigung.
- Auch nach der Freigabe braucht jede Ausfuehrung weiterhin Bestaetigung.
- Es werden keine frei eingegebenen Home-Assistant-Services ausgefuehrt.

Beispiele:

```text
Zeige schaltbare Geraete.
Welche Geraete kann ich freigeben?
Gib Wohnzimmer Licht frei.
Entferne Wohnzimmer Licht aus der Freigabe.
Bestaetige Aktion 1.
```

Lokale Endpunkte:

```text
GET  http://127.0.0.1:8001/assistant/home-assistant/actions/candidates
GET  http://127.0.0.1:8001/assistant/home-assistant/actions/allowlist
POST http://127.0.0.1:8001/assistant/home-assistant/actions/allowlist/add
POST http://127.0.0.1:8001/assistant/home-assistant/actions/allowlist/remove
```

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

## Freihändige Sprachsteuerung: Jarvis

Das bisherige browsergebundene Wake-Word bleibt nur ein optionaler Fallback.
Die robuste Windows-first-Variante ist der `Hammer Jarvis Desktop Agent`.

## Hammer Jarvis Desktop Agent

Hammer Jarvis nutzt bewusst keinen klassischen Windows-Dienst. Ein Dienst läuft
nicht zuverlässig im interaktiven Benutzerkontext und kann Browser/Mikrofon/UI
nicht sauber öffnen. Stattdessen startet ein Desktop-Agent über die
Windows-Aufgabenplanung bei der Benutzeranmeldung.

Eigenschaften:

- Start im Benutzerkontext, RunLevel `Limited`, keine Administratorrechte.
- Genau eine Instanz über `Local\HammerJarvisDesktopAgent`.
- Prüft `http://127.0.0.1:8001/assistant/health`.
- Startet das Backend kontrolliert, falls es nicht läuft.
- Lauscht lokal auf das einzelne Wake Word `Jarvis`.
- Öffnet das Dashboard nur, wenn kein Dashboard verbunden ist.
- Sendet ein Wake-Ereignis an `WebSocket /assistant/desktop/events`.
- Speichert und loggt keine Audiodaten.
- Das Wake Word löst nur die Befehlserkennung aus; alle Aktionen laufen weiter
  über Orchestrator, Permission Layer und Bestätigungsregeln.

Installation:

```powershell
.\scripts\install-desktop-agent.ps1
```

Manuell starten/stoppen/status prüfen:

```powershell
.\scripts\start-desktop-agent.ps1
.\scripts\status-desktop-agent.ps1
.\scripts\stop-desktop-agent.ps1
```

Deinstallation der geplanten Aufgabe:

```powershell
.\scripts\uninstall-desktop-agent.ps1
```

Konfiguration in `.env`:

```text
DESKTOP_AGENT_ENABLED=true
DESKTOP_AGENT_START_BACKEND=true
DESKTOP_AGENT_OPEN_BROWSER_ON_WAKE=true
DESKTOP_AGENT_DASHBOARD_URL=http://127.0.0.1:8001/dashboard
DESKTOP_AGENT_PYTHON_EXECUTABLE=
DESKTOP_AGENT_BACKEND_TIMEOUT_SECONDS=30
DESKTOP_AGENT_DASHBOARD_TIMEOUT_SECONDS=10
DESKTOP_AGENT_READY_ANNOUNCEMENT=true
DESKTOP_AGENT_READY_TEXT=Alle Systeme online und bereit
WAKE_ENGINE=windows_speech
WAKE_WORD=Jarvis
WAKE_CONFIDENCE_THRESHOLD=0.40
WAKE_COOLDOWN_MS=3500
WAKE_LISTENER_READY_TIMEOUT_SECONDS=15
WAKE_RECOGNIZER_CULTURE=auto
WAKE_ACCEPTED_TRANSCRIPTS=Jarvis,Jervis,Dschawis
COMMAND_RECOGNITION_TIMEOUT_MS=9000
```

Der Desktop-Agent und das von ihm gestartete Backend verwenden deterministisch
die Projekt-venv unter `.venv\Scripts`. Bevorzugt wird:

```text
D:\Dev\projects\HammerJarvis\.venv\Scripts\pythonw.exe
```

Falls `pythonw.exe` fehlt, wird `.venv\Scripts\python.exe` genutzt. Ein stiller
Fallback auf globales Python ist nicht erlaubt, wenn die Projekt-venv fehlt
oder der Agent aus einem anderen Interpreter gestartet wurde. Optional kann
`DESKTOP_AGENT_PYTHON_EXECUTABLE` gesetzt werden, muss dann aber auf einen
existierenden lokalen Interpreter zeigen.

Vor dem Backendstart prueft der Agent lokal, ob `fastapi`, `uvicorn` und ein
WebSocket-Transport (`websockets` oder `wsproto`) im ausgewaehlten Interpreter
importierbar sind. `websockets` ist deshalb in `requirements.txt` enthalten.

Wake Engine:

- Standard: `windows_speech`
- Bevorzugte Culture: `de-DE`
- Fallback: `en-US`
- Synchrone Windows-Speech-Schleife im Haupt-Runspace, keine asynchronen
  PowerShell-Callbacks fuer die Wake-Erkennung.
- Grammatik: ausschließlich `Jarvis`, `Jervis` und `Dschawis` als enge
  Aussprachevarianten.
- `WAKE_RECOGNIZER_CULTURE=auto` prueft zuerst `de-DE`, dann `en-US`,
  danach einen anderen installierten Recognizer.
- Fuer den englischen Eigennamen kann `WAKE_RECOGNIZER_CULTURE=en-US`
  gezielt getestet werden.
- `WAKE_ACCEPTED_TRANSCRIPTS=Jarvis,Jervis,Dschawis` erlaubt nur interne
  Aussprachevarianten und normalisiert jedes Wake-Ereignis auf `Jarvis`.

Ein kurzes Einwort-Wake-Word kann Fehlaktivierungen verursachen. Erhöhe bei
Bedarf `WAKE_CONFIDENCE_THRESHOLD`, prüfe Windows-Mikrofoneinstellungen und
installierte Sprachpakete (`de-DE` oder `en-US`). Der Standardwert ist `0.40`.
Für die Kalibrierung ist typischerweise ein Bereich zwischen `0.35` und `0.60`
sinnvoll. Niedrigere Werte erhöhen das Risiko für Fehlaktivierungen.
Windows erkennt die deutsche Aussprache von `Jarvis` teilweise als `Jervis`
oder `Dschawis`; diese Varianten werden intern auf `Jarvis` normalisiert.

Ready-Ansage:

Wenn Agent, Einzelinstanz, Backend, Wake Engine und Event-Brücke bereit sind,
sagt Jarvis einmal pro Agentstart lokal:

```text
Alle Systeme online und bereit
```

Die Ansage nutzt `System.Speech.Synthesis.SpeechSynthesizer` über
`scripts/speak-local.ps1`. Fehler bei der Ansage blockieren den Agent nicht.
Der Agent versucht die Ansage erst, nachdem der Wake Listener eine gültige
JSON-Ready-Nachricht gesendet hat.

Dashboard-Verhalten:

- Wenn ein Dashboard verbunden ist, wird kein neuer Tab geöffnet.
- Wenn kein Dashboard verbunden ist, öffnet der Agent
  `http://127.0.0.1:8001/dashboard?source=desktop-agent`.
- Das Dashboard startet danach die bestehende Browser-Befehlserkennung.
- Die Browser-Befehlserkennung kann je nach Browser einen externen
  Browserdienst verwenden. Hammer Jarvis behauptet daher nicht, dass die
  vollständige Befehlserkennung garantiert offline ist.
- Mikrofonzugriff muss im Browser erlaubt werden.

Lokale Endpunkte:

```text
GET       http://127.0.0.1:8001/assistant/health
GET       http://127.0.0.1:8001/assistant/desktop/status
POST      http://127.0.0.1:8001/assistant/desktop/wake
WebSocket ws://127.0.0.1:8001/assistant/desktop/events
```

Logs:

```text
%LOCALAPPDATA%\HammerJarvis\logs\desktop-agent.log
```

Logs mit UTF-8 lesen:

```powershell
Get-Content -Encoding UTF8 "$env:LOCALAPPDATA\HammerJarvis\logs\desktop-agent.log" -Wait
```

Der Desktop Agent meldet `READY` erst, wenn Backend, Event-Brücke,
Wake-Listener-Prozess, Listener-JSON-Handshake und Prozesszustand bereit sind.
Der Wake Listener muss vorher genau eine JSON-Zeile `type=ready` auf stdout
senden. Diagnoseausgaben gehen nach stderr.

Direkter Wake-Listener-Test ohne Mikrofon:

```powershell
.\scripts\jarvis-wake-listener.ps1 -TestEmitReady
```

Recognizer auflisten:

```powershell
Add-Type -AssemblyName System.Speech
[System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() |
    Select Id,Name,Culture,Description
```

Wake-Diagnose mit automatischer Culture:

```powershell
.\scripts\test-jarvis-wake.ps1 `
    -Culture auto `
    -Threshold 0.40 `
    -DurationSeconds 20 `
    -ShowRecognizedText
```

Wake-Diagnose mit `de-DE`:

```powershell
.\scripts\test-jarvis-wake.ps1 `
    -Culture de-DE `
    -Threshold 0.40 `
    -DurationSeconds 20 `
    -ShowRecognizedText
```

Wake-Diagnose mit `en-US`, sofern installiert:

```powershell
.\scripts\test-jarvis-wake.ps1 `
    -Culture en-US `
    -Threshold 0.40 `
    -DurationSeconds 20 `
    -ShowRecognizedText
```

Während jedes Tests mehrmals deutlich `Jarvis` sagen.

Interpretation:

- `recognized=0`: Mikrofon, Aussprache, Culture oder Recognizer prüfen.
- `rejected>0`: Threshold, Aussprache oder AcceptedTranscripts prüfen.
- Erkanntes `Jervis` oder `Dschawis`: diese Varianten werden intern auf
  `Jarvis` normalisiert.
- `wake_detected > 0`: Wake-Erkennung funktioniert.

Direkter Ansage-Validierungstest ohne Sprechen:

```powershell
.\scripts\speak-local.ps1 -ValidateOnly
```

Manueller End-to-End-Test:

1. Agent stoppen: `.\scripts\stop-desktop-agent.ps1`
2. Wake Listener direkt starten: `.\scripts\test-jarvis-wake.ps1 -Culture auto -Threshold 0.40 -DurationSeconds 20 -ShowRecognizedText`
3. Prüfen, dass eine JSON-Zeile `type=ready` erscheint.
4. `Jarvis` sagen.
5. Prüfen, dass `wake_detected` mit `word=Jarvis` erscheint.
6. Listener mit `Strg+C` beenden.
7. Ansage manuell testen: `.\scripts\speak-local.ps1 -Text "Alle Systeme online und bereit"`
8. Agent starten: `.\scripts\start-desktop-agent.ps1`
9. Log mit `Get-Content -Encoding UTF8 "$env:LOCALAPPDATA\HammerJarvis\logs\desktop-agent.log" -Wait` beobachten.
10. Status prüfen: `.\scripts\status-desktop-agent.ps1`
11. Prüfen, dass `READY` erst nach `wake_listener_ready` erscheint.
12. Prüfen, dass die Bereitschaftsansage genau einmal gesprochen wird.
13. `Jarvis` sagen.
14. Browseröffnung und Befehlserkennung prüfen.
15. Listenerprozess testweise beenden.
16. Prüfen, dass der Agent `DEGRADED` meldet und nur begrenzt neu startet.

Fehlerbehebung:

- Backend nicht erreichbar: `.\scripts\start-jarvis.ps1` oder
  `.\scripts\status-desktop-agent.ps1` prüfen.
- Wake Engine DEGRADED: Windows-Spracherkennung und Sprachpakete prüfen.
- Dashboard öffnet nicht: Standardbrowser und Port `8001` prüfen.
- Browser hört nicht zu: Mikrofonberechtigung für `127.0.0.1` erlauben.
- Bei Standby/Resume kann der Agent den Wake Listener neu starten; Reconnects
  sind begrenzt und laufen nicht in schneller Endlosschleife.

Späteres eigenes openWakeWord-Modell:

`WAKE_ENGINE=openwakeword_custom` ist vorbereitet, wird aber nur genutzt, wenn
`WAKE_WORD_MODEL_PATH=app/data/models/wake/jarvis.onnx` tatsächlich existiert.
Das vorhandene Modell `hey_jarvis` wird nicht stillschweigend als Ersatz für
`Jarvis` verwendet. Modelle werden nicht automatisch heruntergeladen und nicht
ins Repository committed.

## Browser-Wake-Fallback

Das Dashboard kann optional lokal über den Browser-Fallback lauschen. Dieser
Fallback ist nicht der Desktop-Agent und wird im UI entsprechend markiert.
Es werden keine Audiodaten gespeichert oder geloggt.

Die Funktion ist standardmäßig ausgeschaltet. Die normalen Schaltflächen
`Sprechen`, Chat-Eingabe und Sprachausgabe bleiben unverändert nutzbar.

Optionale Installation:

```powershell
.\scripts\setup-wake-word.ps1
```

Danach in `.env` aktivieren:

```text
WAKE_WORD_ENABLED=true
WAKE_WORD=Jarvis
WAKE_WORD_MODEL_PATH=app/data/models/wake/jarvis.onnx
WAKE_WORD_THRESHOLD=0.5
WAKE_WORD_ALLOWED_ORIGINS=http://127.0.0.1:8001;http://localhost:8001
```

Dashboard öffnen:

```text
http://127.0.0.1:8001/dashboard
```

Dann `Browser-Fallback: Ein` anklicken und den Mikrofonzugriff erlauben. Dieser
Fallback nutzt nur ein explizit konfiguriertes eigenes openWakeWord-Modell.
Fehlt `WAKE_WORD_MODEL_PATH`, bleibt der Fallback deaktiviert/degradiert und
fällt nicht auf ein anderes eingebautes Modell zurück. Je nach Browser kann die
anschließende Spracherkennung einen externen Browserdienst verwenden; die
Wake-Erkennung selbst bleibt lokal.

Lokale Endpunkte:

```text
GET       http://127.0.0.1:8001/assistant/voice/wake/status
WebSocket ws://127.0.0.1:8001/assistant/voice/wake/stream
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
- Keine Python-Audiofunktionen im Basissystem. Wake Word ist optional lokal ueber `requirements-voice.txt`.
- Keine PLC-Verbindung
- Keine autonomen Aktionen
- Kein Cloud-Deployment
- Keine OpenAI API Calls
- Kein LangChain
