$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath
$pythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$taskName = "Hammer Jarvis Desktop Agent"

if (Test-Path $pythonw) {
    $interpreter = $pythonw
} elseif (Test-Path $python) {
    $interpreter = $python
} else {
    throw "project_venv_missing: Kein Python-Interpreter in $projectRoot\.venv gefunden. Bitte zuerst die virtuelle Umgebung einrichten und requirements.txt installieren."
}

$action = New-ScheduledTaskAction `
    -Execute $interpreter `
    -Argument "-m app.desktop_agent.main" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Write-Host "Geplante Aufgabe '$taskName' wurde installiert oder aktualisiert."
Write-Host "Start bei Benutzeranmeldung, Benutzerkontext interaktiv, RunLevel Limited."
