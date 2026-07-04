$ErrorActionPreference = "Stop"

$taskName = "Hammer Jarvis Desktop Agent"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if (-not $task) {
    Write-Host "Geplante Aufgabe '$taskName' ist nicht vorhanden. Autostart ist bereits deaktiviert."
    exit 0
}

try {
    Disable-ScheduledTask -TaskName $taskName | Out-Null
    Write-Host "Autostart fuer '$taskName' wurde deaktiviert."
    Write-Host "Hammer Jarvis startet jetzt nur noch manuell, zum Beispiel ueber die Desktop-Verknuepfung."
} catch {
    throw "desktop_agent_autostart_disable_failed: $($_.Exception.Message)"
}
