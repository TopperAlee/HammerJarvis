$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$taskName = "Hammer Jarvis Desktop Agent"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$taskInfo = $null
if ($task) {
    $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
}

$processes = Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*app.desktop_agent.main*" -and $_.CommandLine -like "*$projectRoot*" }

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8001/assistant/health" -TimeoutSec 2
    $backend = $health.status
} catch {
    $backend = "nicht erreichbar"
}

try {
    $desktop = Invoke-RestMethod -Uri "http://127.0.0.1:8001/assistant/desktop/status" -TimeoutSec 2
} catch {
    $desktop = $null
}

Write-Host "Aufgabe installiert: $([bool]$task)"
if ($task) {
    Write-Host "Aufgabe aktiviert: $($task.State -ne 'Disabled')"
    Write-Host "Letzter Start: $($taskInfo.LastRunTime)"
    Write-Host "Letztes Ergebnis: $($taskInfo.LastTaskResult)"
}
Write-Host "Agentprozess vorhanden: $([bool]$processes)"
if ($processes) {
    Write-Host "Agent PID(s): $($processes.ProcessId -join ', ')"
}
    Write-Host "Backend: $backend"
if ($desktop) {
    $listenerStatus = if ($desktop.wake_listener_ready) { "ready" } else { "nicht bereit" }
    $bridgeStatus = if ($desktop.agent_connected) { "ready" } else { "nicht verbunden" }
    $announcementStatus = "nicht versucht"
    if ($desktop.ready_announcement_attempted) {
        $announcementStatus = if ($desktop.ready_announcement_succeeded) { "erfolgreich" } else { "fehlgeschlagen" }
    }

    Write-Host "Agentzustand: $($desktop.agent_state)"
    Write-Host "Agent Python: $($desktop.agent_python)"
    Write-Host "Backend Python: $($desktop.backend_python)"
    Write-Host "Project Root: $($desktop.project_root)"
    Write-Host "WebSocket Transport: $($desktop.websocket_transport)"
    Write-Host "Backend PID: $($desktop.backend_pid)"
    Write-Host "Dashboard-Clients: $($desktop.dashboard_clients)"
    Write-Host "Agent verbunden: $($desktop.agent_connected)"
    Write-Host "Event-Bruecke: $bridgeStatus"
    Write-Host "Wake Listener: $listenerStatus"
    Write-Host "Wake Listener alive: $($desktop.wake_listener_alive)"
    Write-Host "Wake Listener PID: $($desktop.wake_listener_pid)"
    Write-Host "Wake Word: $($desktop.wake_word)"
    Write-Host "Wake Engine: $($desktop.wake_engine)"
    Write-Host "Speech Culture: $($desktop.wake_culture)"
    Write-Host "Recognizer: $($desktop.wake_recognizer)"
    Write-Host "Schwellwert: $($desktop.wake_threshold)"
    Write-Host "Wake ready at: $($desktop.wake_ready_at)"
    Write-Host "Letzte Wake-Erkennung: $($desktop.last_wake_detection_at)"
    Write-Host "Bereitschaftsansage: $announcementStatus"
    if ($desktop.ready_announcement_error) {
        Write-Host "Ansagefehler: $($desktop.ready_announcement_error)"
    }
    if ($desktop.last_error) {
        Write-Host "Fehler: $($desktop.last_error)"
    }
}

Write-Host "Log lesen mit: Get-Content -Encoding UTF8 `"$env:LOCALAPPDATA\HammerJarvis\logs\desktop-agent.log`" -Wait"
