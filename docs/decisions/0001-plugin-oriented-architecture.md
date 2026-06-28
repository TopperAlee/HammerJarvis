# ADR 0001: Plugin-orientierte Engineering-Architektur

## Status

Akzeptiert

## Kontext

HammerJarvis erweitert sich von einem lokalen Assistant Backend zu einem Engineering Assistant fuer Automatisierungstechnik. Die Zielbereiche ProTool, WinCC flexible, TIA Portal, STEP7 Classic, PLC Analysis und Translation QA haben unterschiedliche Datenformate, Sicherheitsrisiken und Entwicklungszyklen.

## Entscheidung

Engineering-Funktionen werden als getrennte Module mit klaren Schnittstellen umgesetzt. Das erste Modul ist `protool`. Weitere Module sollen spaeter als `wincc_flexible`, `tia`, `plc`, `translator` und `diagnostics` folgen.

## Konsequenzen

- Module koennen unabhaengig getestet und erweitert werden.
- Read-only Analyse bleibt pro Modul erzwingbar.
- Dashboard und Assistant-Orchestrierung koennen Module gezielt anbinden.
- Gemeinsame Infrastruktur wie Knowledge, Dateiablage und Reports bleibt wiederverwendbar.

## Verworfene Alternativen

- Ein monolithisches Engineering-Modul: zu schwer wartbar und zu hohes Risiko fuer Seiteneffekte.
- Direkte Integration in den allgemeinen Chat ohne Modulgrenzen: zu wenig nachvollziehbar und schwer sicher zu pruefen.

