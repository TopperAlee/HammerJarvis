$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath
$pythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (Test-Path $pythonw) {
    $interpreter = $pythonw
} elseif (Test-Path $python) {
    $interpreter = $python
} else {
    throw "project_venv_missing: Kein Python-Interpreter in $projectRoot\.venv gefunden. Bitte zuerst python -m venv .venv und .\.venv\Scripts\python.exe -m pip install -r requirements.txt ausfuehren."
}

$existing = Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*app.desktop_agent.main*" -and $_.CommandLine -like "*$projectRoot*" } |
    Select-Object -First 1

if ($existing) {
    Write-Host "Hammer Jarvis Desktop Agent laeuft bereits. PID: $($existing.ProcessId)"
    exit 0
}

Start-Process -FilePath $interpreter `
    -ArgumentList @("-m", "app.desktop_agent.main") `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden

Write-Host "Hammer Jarvis Desktop Agent wurde gestartet."
