# Scripts

Starte Hammer Jarvis lokal unter dem dokumentierten Entwicklungsport `8001`:

```powershell
.\scripts\start-jarvis.ps1
```

Das Skript aktiviert `.venv`, falls die virtuelle Umgebung vorhanden ist, und startet danach:

```powershell
uvicorn app.main:app --reload --port 8001
```
