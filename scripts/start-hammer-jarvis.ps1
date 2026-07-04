$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$healthUrl = "http://127.0.0.1:8001/assistant/health"
$dashboardUrl = "http://127.0.0.1:8001/dashboard"
$backendTimeoutSeconds = 45

function Test-HammerJarvisBackend {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        return ($response.status -eq "ready")
    } catch {
        return $false
    }
}

function Wait-HammerJarvisBackend {
    param(
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HammerJarvisBackend) {
            return $true
        }
        Start-Sleep -Milliseconds 700
    }

    return $false
}

Set-Location $projectRoot

if (-not (Test-Path $python)) {
    throw "project_venv_missing: Kein Python-Interpreter gefunden: $python. Bitte zuerst die virtuelle Umgebung einrichten."
}

if (-not (Test-HammerJarvisBackend)) {
    Write-Host "Hammer Jarvis Backend laeuft nicht. Starte Backend auf Port 8001..."
    Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001") `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden | Out-Null

    if (-not (Wait-HammerJarvisBackend -TimeoutSeconds $backendTimeoutSeconds)) {
        throw "backend_start_timeout: Hammer Jarvis Backend wurde nicht innerhalb von $backendTimeoutSeconds Sekunden bereit. Pruefe die Backend-Konsole oder starte .\scripts\start-jarvis.ps1 manuell."
    }

    Write-Host "Hammer Jarvis Backend ist bereit."
} else {
    Write-Host "Hammer Jarvis Backend laeuft bereits."
}

Write-Host "Oeffne Dashboard: $dashboardUrl"
Start-Process $dashboardUrl
