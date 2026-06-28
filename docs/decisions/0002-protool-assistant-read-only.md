# ADR 0002: ProTool Assistant bleibt read-only

## Status

Akzeptiert

## Kontext

ProTool-Projekte und CSV-Exporte koennen produktionsrelevante HMI-Texte enthalten. Eine automatische Veraenderung alter Projektdateien waere riskant, insbesondere bei Encoding, Platzhaltern, Panelgrenzen und mehrzeiligen Feldern.

## Entscheidung

Der ProTool Assistant analysiert CSV-Dateien nur lesend. Er schreibt keine CSV-Dateien zurueck, erzeugt keine Uebersetzungen und veraendert keine Projektdateien. Ergebnisse werden als JSON-Report und Dashboard-Anzeige ausgegeben.

## Konsequenzen

- Analyse ist sicherer und reproduzierbarer.
- Originaldateien bleiben unveraendert.
- Reports koennen fuer manuelle Engineering-Entscheidungen genutzt werden.
- Schreibende Funktionen erfordern spaeter eine eigene Sicherheitsentscheidung.

## Verworfene Alternativen

- Automatisches Zurueckschreiben korrigierter CSV-Dateien: zu hohes Risiko fuer Encoding- und Formatfehler.
- Automatische Uebersetzung im v0.3.x-Umfang: fachlich und sicherheitstechnisch zu frueh.

