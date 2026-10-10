# Richtet die Tunnel-Aufgaben neu ein:
#  1. "Strato-Tunnel PC"          - startet bei Anmeldung, OHNE Terminal-Fenster
#                                   (conhost --headless; -WindowStyle Hidden wird
#                                   vom Windows Terminal unter Win11 ignoriert)
#  2. "Strato-Tunnel PC Wächter"  - alle 5 Min.: Tunnel tot -> Aufgabe 1 starten
# Ersetzt vorhandene Aufgaben gleichen Namens. Der Tunnel ist dabei für wenige
# Sekunden unterbrochen (laufender Automatik-Lauf wiederholt nach 5 Min.).

$ErrorActionPreference = 'Stop'
$ordner = $PSScriptRoot
$conhost = "$env:SystemRoot\System32\conhost.exe"
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

function Neu-Aufgabe($name, $skript, $ausloeser, $einst) {
    $arg = "--headless `"$ps`" -NoProfile -ExecutionPolicy Bypass -File `"$ordner\$skript`""
    $aktion = New-ScheduledTaskAction -Execute $conhost -Argument $arg
    Register-ScheduledTask -TaskName $name -Action $aktion -Trigger $ausloeser `
        -Settings $einst -Force | Out-Null
}

# Alte Instanz (inkl. sichtbarem Fenster) und zugehörigen ssh beenden
Stop-ScheduledTask -TaskName "Strato-Tunnel PC" -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
    Where-Object { $_.CommandLine -like '*strato_tunnel_pc*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$tunnelEinst = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Neu-Aufgabe "Strato-Tunnel PC" "strato-tunnel.ps1" `
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) $tunnelEinst

$waechterEinst = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$waechterTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5)
Neu-Aufgabe "Strato-Tunnel PC Wächter" "strato-tunnel-waechter.ps1" $waechterTrigger $waechterEinst

Start-ScheduledTask -TaskName "Strato-Tunnel PC"
Start-Sleep -Seconds 10
$ok = Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
    Where-Object { $_.CommandLine -like '*strato_tunnel_pc*' }
if ($ok) { "OK: Tunnel läuft (ssh PID $($ok.ProcessId)), Wächter aktiv." }
else { "FEHLER: ssh läuft nicht - Log prüfen: $env:LOCALAPPDATA\strato-tunnel-pc.log" }
