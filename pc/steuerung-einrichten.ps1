# Richtet den Steuer-Dienst auf dem PC ein (einmalig):
#  - erzeugt den Token (falls noch keiner da ist) und speichert Pfade in
#    %LOCALAPPDATA%\ge-steuerung\
#  - legt die Aufgabe "Steuerung PC" an (startet bei Anmeldung, ohne Fenster)
#  - startet sie und prüft den Dienst
# Danach den ausgegebenen Token im Tab "KI-Ziele" beim Ziel "PC (Tunnel)"
# eintragen (Steuer-Port 18332) - und VORHER auf Strato `localhost:18332` in
# die PermitOpen-Zeile aufnehmen (siehe pc/README.md).

$ErrorActionPreference = 'Stop'
$ordner = Join-Path $env:LOCALAPPDATA "ge-steuerung"
New-Item -ItemType Directory -Force $ordner | Out-Null

# Python + Docker Desktop finden
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "python nicht gefunden (PATH)" }
$docker = Get-Command docker -ErrorAction SilentlyContinue
$dockerExe = ""
if ($docker) {
    # ...\<Programm>\resources\bin\docker.exe  ->  ...\<Programm>\Docker Desktop.exe
    $kandidat = Join-Path (Split-Path (Split-Path (Split-Path $docker.Source))) "Docker Desktop.exe"
    if (Test-Path $kandidat) { $dockerExe = $kandidat }
}
if (-not $dockerExe) {
    $kandidat = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $kandidat) { $dockerExe = $kandidat }
}
if (-not $dockerExe) { Write-Warning "Docker Desktop.exe nicht gefunden - der Knopf kann Docker dann nicht selbst starten." }

@{ python = $python; dockerDesktop = $dockerExe } | ConvertTo-Json | Set-Content (Join-Path $ordner "konfig.json") -Encoding UTF8

$tokenDatei = Join-Path $ordner "token"
if (-not (Test-Path $tokenDatei)) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    ([BitConverter]::ToString($bytes) -replace '-', '').ToLower() | Set-Content $tokenDatei -Encoding ASCII
    "Neuen Token erzeugt."
}

# Aufgabe
$conhost = "$env:SystemRoot\System32\conhost.exe"
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$skript = Join-Path $PSScriptRoot "steuerung-dienst.ps1"
$aktion = New-ScheduledTaskAction -Execute $conhost `
    -Argument "--headless `"$ps`" -NoProfile -ExecutionPolicy Bypass -File `"$skript`""
$einst = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Stop-ScheduledTask -TaskName "Steuerung PC" -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "Steuerung PC" -Action $aktion `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) -Settings $einst -Force | Out-Null
Start-ScheduledTask -TaskName "Steuerung PC"
Start-Sleep -Seconds 6

$token = (Get-Content $tokenDatei -Raw).Trim()
try {
    $s = Invoke-RestMethod -Uri "http://127.0.0.1:7862/status" -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 20
    "OK: Steuer-Dienst läuft. Docker aktiv: $($s.docker); Container: " + (($s.containers | ForEach-Object { "$($_.name)=$($_.running)" }) -join ", ")
} catch {
    "FEHLER: Dienst antwortet nicht - Log: $ordner\steuerung.log"
    return
}
""
"Token für das KI-Ziel 'PC (Tunnel)' (Steuer-Port 18332):"
$token
