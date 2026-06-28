# ADR 0003: Browser-Upload fuer lokale Dateien

## Status

Akzeptiert

## Kontext

Browser liefern bei Dateiauswahl aus Sicherheitsgruenden keinen echten lokalen Dateipfad. Ein Backend-Endpoint, der nur `file_path` akzeptiert, kann daher nicht zuverlaessig mit einem Datei-Auswahldialog im Dashboard verwendet werden.

## Entscheidung

Fuer browserbasierte Dateiauswahl wird ein Multipart-Upload-Endpoint verwendet. Der Browser sendet die Datei als `FormData`; das Backend speichert sie temporaer in einem lokalen Upload-/Workspace-Ordner und ruft danach dieselbe Analysefunktion auf wie beim manuellen Dateipfad.

## Konsequenzen

- Der Button `Durchsuchen` funktioniert ohne Fake-Pfad.
- Die bestehende Pfad-basierte Analyse bleibt fuer manuell eingegebene lokale Pfade erhalten.
- Validierungslogik wird nicht dupliziert.
- Upload-Kopien sind temporaere Arbeitsdateien und ersetzen nicht die Originaldatei.

## Verworfene Alternativen

- Dateinamen aus dem Browser als echten Pfad interpretieren: funktioniert nicht zuverlaessig und ist irrefuehrend.
- Browser-spezifische Pfad-Hacks: unsicher, unportabel und nicht mit modernen Browser-Sicherheitsmodellen vereinbar.

