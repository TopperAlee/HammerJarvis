$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath
$desktop = [Environment]::GetFolderPath("DesktopDirectory")
$shortcutPath = Join-Path $desktop "Hammer Jarvis.lnk"
$launcherPath = Join-Path $projectRoot "scripts\start-hammer-jarvis.ps1"
$powershellPath = Join-Path $PSHOME "powershell.exe"

if (-not (Test-Path $launcherPath)) {
    throw "launcher_missing: Startskript nicht gefunden: $launcherPath"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershellPath
$shortcut.Arguments = "-ExecutionPolicy Bypass -File `"$launcherPath`""
$shortcut.WorkingDirectory = $projectRoot

$iconCandidates = @(
    (Join-Path $projectRoot "app\static\favicon.ico"),
    (Join-Path $projectRoot "app\static\hammer-jarvis.ico")
)
$iconPath = $iconCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iconPath) {
    $shortcut.IconLocation = $iconPath
}

$shortcut.Save()

Write-Host "Desktop-Verknuepfung erstellt: $shortcutPath"
Write-Host "Ziel: $powershellPath $($shortcut.Arguments)"
