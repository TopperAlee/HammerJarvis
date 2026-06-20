param(
    [string]$Culture = "auto",
    [double]$Threshold = 0.40,
    [int]$DurationSeconds = 15,
    [switch]$ShowRecognizedText
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

Write-Host "Hammer Jarvis Wake-Diagnose"
Write-Host "Sagen Sie jetzt mehrmals deutlich: Jarvis"
Write-Host "Culture: $Culture"
Write-Host "Threshold: $Threshold"
Write-Host "Dauer: $DurationSeconds Sekunden"
Write-Host ""

$listener = Join-Path $PSScriptRoot "jarvis-wake-listener.ps1"
$arguments = @(
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $listener,
    "-Diagnostics",
    "-ProbeSeconds",
    [string]$DurationSeconds,
    "-RecognizerCulture",
    $Culture,
    "-ConfidenceThreshold",
    [string]$Threshold
)
if ($ShowRecognizedText) {
    $arguments += "-ShowRecognizedText"
}

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = "powershell.exe"
function ConvertTo-NativeArgument {
    param(
        [AllowEmptyString()]
        [string]$Value
    )

    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    return '"' + ($Value -replace '"', '\"') + '"'
}

$psi.Arguments = (
    $arguments |
        ForEach-Object {
            ConvertTo-NativeArgument -Value ([string]$_)
        }
) -join ' '
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
$psi.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $psi
[void]$process.Start()

$stdout = $process.StandardOutput.ReadToEnd()
$stderr = $process.StandardError.ReadToEnd()
$process.WaitForExit()

if ($stdout) {
    Write-Host $stdout.TrimEnd()
}
if ($stderr) {
    [Console]::Error.WriteLine($stderr.TrimEnd())
}

$summaryCount = 0
$summary = $null
foreach ($line in ($stdout -split "`r?`n")) {
    if (-not $line.Trim()) { continue }
    try {
        $event = $line | ConvertFrom-Json -ErrorAction Stop
    } catch {
        continue
    }
    if ($event.type -eq "diagnostic_summary") {
        $summaryCount += 1
        $summary = $event
    }
}

if ($process.ExitCode -ne 0) {
    Write-Error "Wake-Diagnose fehlgeschlagen. Exitcode: $($process.ExitCode)"
    exit $process.ExitCode
}
if ($summaryCount -ne 1) {
    Write-Error "Wake-Diagnose unvollstaendig: diagnostic_summary wurde nicht genau einmal erzeugt."
    exit 6
}
if (-not $summary.completed) {
    Write-Error "Wake-Diagnose meldet completed=false."
    exit 7
}

Write-Host ""
Write-Host "Interpretation:"
Write-Host "- recognized=0: Mikrofon, Aussprache, Culture oder Recognizer pruefen."
Write-Host "- rejected>0: Threshold, Aussprache oder AcceptedTranscripts pruefen."
Write-Host "- erkannte Jervis/Dschawis gelten als gueltige interne Varianten."
Write-Host "- wake_detected > 0: Wake-Erkennung funktioniert."
Write-Host "Moeglicher naechster Schritt: Threshold vorsichtig zwischen 0.35 und 0.60 kalibrieren, nicht automatisch."
exit 0
