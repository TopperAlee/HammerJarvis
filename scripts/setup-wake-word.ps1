$ErrorActionPreference = "Stop"

$python = "python"
if (Test-Path ".\.venv\Scripts\python.exe") {
    $python = ".\.venv\Scripts\python.exe"
}

Write-Host "Installiere optionale Wake-Word-Abhaengigkeiten..."
& $python -m pip install -r requirements-voice.txt

Write-Host "Pruefe openWakeWord-Import..."
& $python -c "import openwakeword, numpy; from openwakeword.model import Model; print('openWakeWord ist importierbar.')"

Write-Host ""
Write-Host "Fertig. Standard bleibt der Desktop-Agent mit Windows Speech:"
Write-Host "WAKE_ENGINE=windows_speech"
Write-Host "WAKE_WORD=Jarvis"
Write-Host ""
Write-Host "Optionales eigenes openWakeWord-Modell aktivieren, wenn die Datei existiert:"
Write-Host "WAKE_ENGINE=openwakeword_custom"
Write-Host "WAKE_WORD=Jarvis"
Write-Host "WAKE_WORD_MODEL_PATH=app/data/models/wake/jarvis.onnx"
Write-Host ""
Write-Host "Hinweis: Die Browser-Spracherkennung nach dem Weckwort nutzt weiterhin die Web Speech API des Browsers."
