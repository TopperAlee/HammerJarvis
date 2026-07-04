$ErrorActionPreference = "Stop"

$connections = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -eq "127.0.0.1" }

if (-not $connections) {
    Write-Host "Kein Hammer Jarvis Backend auf 127.0.0.1:8001 gefunden."
    exit 0
}

$processIds = $connections |
    Select-Object -ExpandProperty OwningProcess -Unique |
    Where-Object { $_ -and $_ -gt 0 }

if (-not $processIds) {
    Write-Host "Port 8001 ist belegt, aber kein Prozess konnte ermittelt werden."
    exit 1
}

foreach ($processId in $processIds) {
    try {
        Stop-Process -Id $processId -ErrorAction Stop
        Write-Host "Hammer Jarvis Backend auf 127.0.0.1:8001 gestoppt. PID: $processId"
    } catch {
        throw "backend_stop_failed: Prozess $processId konnte nicht beendet werden. $($_.Exception.Message)"
    }
}
