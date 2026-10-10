# Wächter für den Strato-Tunnel: wird alle 5 Minuten von der Aufgabe
# "Strato-Tunnel PC Wächter" gestartet und startet die Tunnel-Aufgabe neu,
# falls weder die Aufgabe läuft noch ein passender ssh-Prozess existiert.

$aufgabe = "Strato-Tunnel PC"
$log = "$env:LOCALAPPDATA\strato-tunnel-pc.log"

$ssh = Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
    Where-Object { $_.CommandLine -like '*strato_tunnel_pc*' }
if ($ssh) { exit 0 }

# Läuft die Aufgabe, ist die Schleife gerade nur im 5-s-Neustart-Warten.
if ((Get-ScheduledTask -TaskName $aufgabe).State -eq 'Running') { exit 0 }

"$(Get-Date -Format s) Wächter: Tunnel nicht aktiv, starte Aufgabe neu" | Add-Content $log
Start-ScheduledTask -TaskName $aufgabe
