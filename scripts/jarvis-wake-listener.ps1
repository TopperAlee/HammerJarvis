param(
    [string]$WakeWord = "Jarvis",
    [double]$ConfidenceThreshold = 0.40,
    [string]$RecognizerCulture = "auto",
    [string]$AcceptedTranscripts = "Jarvis,Jervis,Dschawis",
    [switch]$Diagnostics,
    [int]$ProbeSeconds = 0,
    [switch]$ShowRecognizedText,
    [switch]$TestEmitReady
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$recognizedCount = 0
$rejectedCount = 0
$wakeDetectedCount = 0

function Write-JsonEvent {
    param([hashtable]$Event)
    $json = $Event | ConvertTo-Json -Compress
    [Console]::Out.WriteLine($json)
    [Console]::Out.Flush()
}

function Write-Diagnostic {
    param([string]$Message)
    if ($Diagnostics) {
        [Console]::Error.WriteLine($Message)
        [Console]::Error.Flush()
    }
}

function Get-RecognizerInventory {
    param($Recognizers)
    @($Recognizers | ForEach-Object {
        @{
            id = [string]$_.Id
            name = [string]$_.Name
            culture = [string]$_.Culture.Name
            description = [string]$_.Description
        }
    })
}

function Select-RecognizerInfo {
    param(
        $Recognizers,
        [string]$Culture
    )
    if (-not $Recognizers -or $Recognizers.Count -eq 0) {
        return $null
    }
    if ($Culture -eq "auto") {
        $match = $Recognizers | Where-Object { $_.Culture.Name -eq "de-DE" } | Select-Object -First 1
        if ($match) { return $match }
        $match = $Recognizers | Where-Object { $_.Culture.Name -eq "en-US" } | Select-Object -First 1
        if ($match) { return $match }
        return $Recognizers | Select-Object -First 1
    }
    return $Recognizers | Where-Object { $_.Culture.Name -eq $Culture } | Select-Object -First 1
}

function Get-AcceptedTranscriptList {
    param([string]$Value)
    $seen = @{}
    $items = New-Object System.Collections.Generic.List[string]
    foreach ($part in ($Value -split ",")) {
        $phrase = ($part -replace "\s+", " ").Trim()
        if (-not $phrase) { continue }
        if ($phrase.ToLowerInvariant() -eq "hey jarvis") { continue }
        if ($phrase.ToLowerInvariant() -eq "okay jarvis") { continue }
        if ($phrase.ToLowerInvariant() -eq "hallo jarvis") { continue }
        $key = $phrase.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        [void]$items.Add($phrase)
    }
    if ($items.Count -eq 0) {
        [void]$items.Add("Jarvis")
    }
    return $items.ToArray()
}

function Test-AcceptedTranscript {
    param(
        [string]$Text,
        [string[]]$AcceptedTranscripts
    )
    foreach ($phrase in $AcceptedTranscripts) {
        if ($Text.Equals($phrase, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function New-GrammarForJarvis {
    param(
        [string[]]$Transcripts,
        $Culture
    )
    $choices = [System.Speech.Recognition.Choices]::new()
    foreach ($transcript in $Transcripts) {
        [void]$choices.Add($transcript)
    }
    $builder = [System.Speech.Recognition.GrammarBuilder]::new()
    $builder.Culture = $Culture
    $builder.Append($choices)
    return [System.Speech.Recognition.Grammar]::new($builder)
}

function Get-MicrophoneErrorCode {
    param([string]$Message)
    $lower = $Message.ToLowerInvariant()
    if ($lower -like "*access*denied*" -or $lower -like "*zugriff*verweigert*") { return "microphone_access_denied" }
    if ($lower -like "*busy*" -or $lower -like "*verwendet*") { return "audio_device_busy" }
    if ($lower -like "*no default*" -or $lower -like "*kein standard*") { return "no_default_audio_device" }
    return "audio_input_initialization_failed"
}

function Write-DiagnosticSummary {
    param(
        [bool]$Completed,
        [string]$ErrorText = $null
    )
    if ($Diagnostics -and $ProbeSeconds -gt 0) {
        Write-JsonEvent @{
            type = "diagnostic_summary"
            duration_seconds = $ProbeSeconds
            recognizer = if ($recognizerInfo) { [string]$recognizerInfo.Name } else { $null }
            culture = if ($recognizerInfo) { [string]$recognizerInfo.Culture.Name } else { $null }
            threshold = $ConfidenceThreshold
            recognized = $recognizedCount
            rejected = $rejectedCount
            wake_detected = $wakeDetectedCount
            completed = $Completed
            error = $ErrorText
        }
    }
}

try {
    if ($WakeWord -ne "Jarvis") {
        Write-JsonEvent @{
            type = "error"
            code = "invalid_wake_word"
            message = "Nur das Wake Word Jarvis ist erlaubt."
        }
        exit 2
    }

    if ($ConfidenceThreshold -lt 0.10) { $ConfidenceThreshold = 0.10 }
    if ($ConfidenceThreshold -gt 0.99) { $ConfidenceThreshold = 0.99 }
    $accepted = Get-AcceptedTranscriptList $AcceptedTranscripts

    if ($TestEmitReady) {
        Write-JsonEvent @{
            type = "ready"
            engine = "windows_speech"
            wake_word = "Jarvis"
            culture = "de-DE"
            recognizer = "Test Recognizer"
            threshold = $ConfidenceThreshold
            accepted_transcripts = $accepted
            audio_input = "default"
            timestamp = [DateTimeOffset]::UtcNow.ToString("o")
        }
        exit 0
    }

    Add-Type -AssemblyName System.Speech
    $recognizers = @([System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers())
    $inventory = Get-RecognizerInventory $recognizers

    if ($Diagnostics) {
        Write-Diagnostic "Recognizer inventory:"
        foreach ($item in $inventory) {
            Write-Diagnostic "id=$($item.id) name=$($item.name) culture=$($item.culture) description=$($item.description)"
        }
        Write-Diagnostic "requested_culture=$RecognizerCulture wake_word=Jarvis threshold=$ConfidenceThreshold"
        Write-Diagnostic "accepted_transcripts=$($accepted -join ', ')"
        Write-JsonEvent @{
            type = "recognizer_inventory"
            recognizers = $inventory
        }
    }

    if ($recognizers.Count -eq 0) {
        Write-JsonEvent @{
            type = "error"
            code = "recognizer_unavailable"
            message = "Kein Windows-Spracherkenner installiert."
        }
        Write-DiagnosticSummary -Completed $false -ErrorText "recognizer_unavailable"
        exit 2
    }

    $recognizerInfo = Select-RecognizerInfo -Recognizers $recognizers -Culture $RecognizerCulture
    if (-not $recognizerInfo) {
        Write-JsonEvent @{
            type = "error"
            code = "culture_not_installed"
            message = "Die gewuenschte Recognizer-Culture ist nicht installiert."
            requested_culture = $RecognizerCulture
            installed_cultures = @($inventory | ForEach-Object { $_.culture })
        }
        Write-DiagnosticSummary -Completed $false -ErrorText "culture_not_installed"
        exit 3
    }

    Write-Diagnostic "selected_recognizer=$($recognizerInfo.Name) culture=$($recognizerInfo.Culture.Name)"
    $engine = [System.Speech.Recognition.SpeechRecognitionEngine]::new($recognizerInfo)
    $grammar = New-GrammarForJarvis -Transcripts $accepted -Culture $recognizerInfo.Culture
    $engine.LoadGrammar($grammar)

    try {
        $engine.SetInputToDefaultAudioDevice()
    }
    catch {
        $code = Get-MicrophoneErrorCode $_.Exception.Message
        Write-Diagnostic "microphone_error code=$code message=$($_.Exception.Message)"
        Write-JsonEvent @{
            type = "error"
            code = $code
            message = "Der Standard-Audioeingang konnte nicht initialisiert werden."
        }
        Write-DiagnosticSummary -Completed $false -ErrorText $code
        exit 4
    }

    Write-JsonEvent @{
        type = "ready"
        engine = "windows_speech"
        wake_word = "Jarvis"
        culture = $recognizerInfo.Culture.Name
        recognizer = $recognizerInfo.Name
        threshold = $ConfidenceThreshold
        accepted_transcripts = $accepted
        audio_input = "default"
        timestamp = [DateTimeOffset]::UtcNow.ToString("o")
    }

    $started = [DateTimeOffset]::UtcNow
    while ($true) {
        try {
            $result = $engine.Recognize([TimeSpan]::FromMilliseconds(750))
        }
        catch {
            Write-Diagnostic "recognition_failed message=$($_.Exception.Message)"
            Write-JsonEvent @{
                type = "error"
                code = "recognition_failed"
                message = "Die Windows-Spracherkennung ist fehlgeschlagen."
            }
            Write-DiagnosticSummary -Completed $false -ErrorText "recognition_failed"
            exit 5
        }

        if ($null -ne $result) {
            $text = [string]$result.Text
            $confidence = [Math]::Round([double]$result.Confidence, 3)
            $acceptedMatch = Test-AcceptedTranscript -Text $text -AcceptedTranscripts $accepted
            $recognizedCount += 1

            if ($Diagnostics -and $ShowRecognizedText) {
                Write-Diagnostic "recognized_text=$text confidence=$confidence accepted=$acceptedMatch"
            }

            if ($acceptedMatch -and $confidence -ge $ConfidenceThreshold) {
                $wakeDetectedCount += 1
                Write-JsonEvent @{
                    type = "wake_detected"
                    engine = "windows_speech"
                    culture = $recognizerInfo.Culture.Name
                    word = "Jarvis"
                    recognized_as = $text
                    confidence = $confidence
                    timestamp = [DateTimeOffset]::UtcNow.ToString("o")
                }
            } else {
                $rejectedCount += 1
            }
        }

        if ($Diagnostics -and $ProbeSeconds -gt 0 -and ([DateTimeOffset]::UtcNow - $started).TotalSeconds -ge $ProbeSeconds) {
            Write-DiagnosticSummary -Completed $true
            break
        }
    }

    exit 0
}
catch {
    Write-Diagnostic $_.Exception.Message
    Write-JsonEvent @{
        type = "error"
        code = "wake_listener_failed"
        message = "Windows-Speech-Wake-Listener fehlgeschlagen."
    }
    Write-DiagnosticSummary -Completed $false -ErrorText "wake_listener_failed"
    exit 1
}
finally {
    if ($engine) {
        $engine.Dispose()
    }
}
