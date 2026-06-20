$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$processes = Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*app.desktop_agent.main*" -and $_.CommandLine -like "*$projectRoot*" }

if (-not $processes) {
    Write-Host "Hammer Jarvis Desktop Agent laeuft nicht."
    exit 0
}

foreach ($process in $processes) {
    Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
    Write-Host "Desktop-Agent gestoppt. PID: $($process.ProcessId)"
}
