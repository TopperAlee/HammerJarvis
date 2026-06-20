param(
    [Parameter(Mandatory = $false)]
    [string]$Text,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

try {
    Add-Type -AssemblyName System.Speech
    $speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
    $voices = $speaker.GetInstalledVoices()
    $germanVoice = $voices |
        Where-Object { $_.VoiceInfo.Culture.Name -like "de-*" } |
        Select-Object -First 1
    if ($germanVoice) {
        $speaker.SelectVoice($germanVoice.VoiceInfo.Name)
    }

    if ($ValidateOnly) {
        exit 0
    }

    if ([string]::IsNullOrWhiteSpace($Text)) {
        [Console]::Error.WriteLine("Parameter -Text ist erforderlich.")
        exit 2
    }

    $speaker.Rate = 0
    $speaker.Volume = 100
    $speaker.Speak($Text)
    exit 0
}
catch {
    [Console]::Error.WriteLine("Lokale Sprachausgabe fehlgeschlagen: $($_.Exception.Message)")
    exit 1
}
finally {
    if ($speaker) {
        $speaker.Dispose()
    }
}
