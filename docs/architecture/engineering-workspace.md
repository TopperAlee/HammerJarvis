# Engineering Workspace Foundation

Der Engineering Workspace ist die gemeinsame Plattform fuer zukuenftige HammerJarvis-Module rund um Automatisierungstechnik. In Milestone 4.0 werden noch keine neuen Siemens-Dateiformate geparst. Der Fokus liegt auf Struktur, Erweiterbarkeit und einer gemeinsamen Dashboard-Fläche.

## Plugin-Konzept

Engineering-Funktionen werden als Module registriert. Die Registry liegt in `hammer_jarvis/engineering/plugins.py` und beschreibt zunaechst nur bekannte Module:

- `protool`
- `wincc_flexible`
- `tia`
- `step7`
- `translator`
- `diagnostics`

Die Registry enthaelt bewusst keine Parser- oder Ausfuehrungslogik. Sie dient als stabile Grundlage fuer API, Dashboard und spaetere Modulaktivierung.

## Datenmodell

Das gemeinsame Datenmodell liegt in `hammer_jarvis/engineering/models.py`. Es definiert die grundlegenden Begriffe, die mehrere Engineering-Module teilen koennen:

- `Project`
- `ProjectFile`
- `Variable`
- `TextResource`
- `Alarm`
- `Recipe`
- `ProgramBlock`
- `Reference`

Die Modelle sind aktuell reine Dataclasses. Sie enthalten keine Dateizugriffe und keine Siemens-spezifischen Parser. Dadurch bleiben sie leicht testbar und koennen spaeter von ProTool, WinCC flexible, TIA Portal oder STEP7 Classic gemeinsam genutzt werden.

## API

Der Workspace stellt zwei read-only Endpunkte bereit:

- `GET /assistant/engineering/modules`
- `GET /assistant/engineering/projects`

`/assistant/engineering/modules` liefert die registrierten Engineering-Module.  
`/assistant/engineering/projects` liefert vorerst Demo-Daten fuer den Project Explorer.

## Dashboard

Das Dashboard enthaelt einen neuen Bereich `Engineering` mit drei Zonen:

- links: Project Explorer
- Mitte: Arbeitsbereich
- rechts: Eigenschaften

Die Bereiche `Projekte`, `HMI`, `PLC`, `Übersetzung` und `Dokumentation` sind Platzhalter fuer spaetere Module. Der bestehende ProTool Assistant bleibt unveraendert als funktionsfaehiges read-only Modul erhalten.

## Erweiterbarkeit

Spaetere Milestones koennen dynamische Projektquellen anschliessen, ohne die Dashboard-Struktur oder die API-Grundform zu ersetzen:

1. Parser liefern `Project`-Objekte.
2. Module registrieren sich in der Engineering Registry.
3. API-Endpunkte geben strukturierte Projektdaten aus.
4. Das Dashboard rendert Project Explorer, Arbeitsbereich und Eigenschaften aus demselben Modell.

Alle neuen Engineering-Funktionen starten read-only. Schreibende oder produktionsrelevante Funktionen brauchen eine eigene Sicherheitsentscheidung.

