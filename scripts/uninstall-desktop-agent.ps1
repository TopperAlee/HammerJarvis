$ErrorActionPreference = "Stop"

$taskName = "Hammer Jarvis Desktop Agent"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Geplante Aufgabe '$taskName' ist nicht installiert."
    exit 0
}

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host "Geplante Aufgabe '$taskName' wurde entfernt. Projektdateien und Logs wurden nicht geloescht."
