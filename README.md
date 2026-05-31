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
uvicorn app.main:app --reload
```

## Browser URLs

- API Startseite: `http://127.0.0.1:8000/`
- Swagger UI: `http://127.0.0.1:8000/docs`
- Home Assistant Entities: `http://127.0.0.1:8000/ha/entities`
- Nicht verfuegbare Entities: `http://127.0.0.1:8000/ha/unavailable`
- Klassifizierte Home Assistant Probleme: `http://127.0.0.1:8000/ha/problems`
- EcoFlow Diagnose: `http://127.0.0.1:8000/ha/ecoflow`
- EcoFlow Energieuebersicht: `http://127.0.0.1:8000/ha/ecoflow/energy`
- Energie-/Leistungswerte: `http://127.0.0.1:8000/ha/power`

## Dashboard oeffnen

Das lokale Dashboard ist nach dem Serverstart im Browser erreichbar:

```text
http://127.0.0.1:8000/dashboard
```

## Sprachsteuerung

Oeffne das lokale Dashboard unter `http://127.0.0.1:8000/dashboard`.
Klicke auf `Sprechen`, erlaube den Mikrofonzugriff im Browser und sprich einen Befehl.
Jarvis zeigt den erkannten Befehl und die Antwort im Dashboard an und gibt die Antwort per Sprachausgabe aus, wenn die Sprachausgabe eingeschaltet ist.

Die Sprachsteuerung nutzt die Web Speech API des Browsers.
Falls die Spracherkennung nicht verfuegbar ist, verwende Chrome oder Edge.
Es gibt in v0.2 noch kein Wake Word und keinen Always-Listening-Modus.

## Testen mit `/docs`

Oeffne `http://127.0.0.1:8000/docs` im Browser.
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

## Tests

```powershell
python -m pytest
```

Die Tests verwenden keinen echten Home Assistant Server.

## Aktuelle Einschraenkungen v0.1

- Kein Frontend
- Kein Docker
- Keine Datenbank
- Keine Voice-Assistant-Funktionen
- Keine PLC-Verbindung
- Keine autonomen Aktionen
- Kein Cloud-Deployment
- Keine OpenAI API Calls
- Kein LangChain
