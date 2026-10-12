# Steuer-Dienst auf dem PC: lässt die App (Prod, über den Reverse-Tunnel) Docker
# Desktop und den Ollama-Container starten und die installierten Modelle
# scannen ("KI starten & Modelle scannen" in den Einstellungen).
# Dasselbe Programm wie auf Athene (athene/steuerung/app.py), hier mit
# Windows-RAM-Abfrage und DOCKER_DESKTOP_EXE. Lauscht NUR auf 127.0.0.1:7862;
# nach außen geht es ausschließlich über den Reverse-Tunnel (Strato :18332) und
# braucht den Bearer-Token aus %LOCALAPPDATA%\ge-steuerung\token.
# Gestartet per Aufgabenplanung bei der Anmeldung (Einrichtung:
# pc/steuerung-einrichten.ps1), Endlosschleife wie strato-tunnel.ps1.

$ordner = Join-Path $env:LOCALAPPDATA "ge-steuerung"
$log = Join-Path $ordner "steuerung.log"
$app = Join-Path (Split-Path $PSScriptRoot -Parent) "athene\steuerung\app.py"
$konfig = Join-Path $ordner "konfig.json"
$k = Get-Content $konfig -Raw | ConvertFrom-Json

$env:STEUERUNG_PORT = "7862"
$env:STEUERUNG_TOKEN_FILE = Join-Path $ordner "token"
# Ollama plus die Bild-KIs von BildKI (D:\KI-Server\Dienste\bild-kis*.yaml): Ollama und Bild-KIs teilen sich die
# 16 GB VRAM der RTX 5070 Ti. Mit den sd-server-Namen kann die Speicherkontrolle der App (Einstellungen: Container)
# laufende Bild-KIs sehen und vor dem Schreiben stoppen.
$env:STEUERBARE_CONTAINER = "ollama,sd-server,sd-server-pony,sd-server-dev,sd-server-kontext"
$env:DOCKER_DESKTOP_EXE = $k.dockerDesktop
$env:PYTHONIOENCODING = "utf-8"

while ($true) {
    "$(Get-Date -Format s) Steuer-Dienst startet" | Add-Content $log
    & $k.python $app 2>&1 | Add-Content $log
    "$(Get-Date -Format s) Steuer-Dienst beendet (Exit $LASTEXITCODE), Neustart in 5 s" | Add-Content $log
    Start-Sleep -Seconds 5
}
