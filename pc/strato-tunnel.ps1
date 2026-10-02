# Reverse-SSH-Tunnel PC -> Strato, damit Prod (geschichten.daniel-ertl.de)
# das Ollama auf diesem PC nutzen kann. Gegenstück zu
# athene/systemd/strato-tunnel.service; Windows hat kein systemd, daher
# eine Endlosschleife, die per Aufgabenplanung bei der Anmeldung startet
# (Einrichtung siehe pc/README.md).
#
# Port-Zuordnung:  Strato 127.0.0.1:18331  ->  PC 127.0.0.1:11434 (Ollama)
# 18331 MUSS auf Strato im "Match User tunnel"-Block als
# "PermitOpen localhost:18331" stehen, sonst bricht der Tunnel wegen
# ExitOnForwardFailure sofort ab.

$ssh = "$env:SystemRoot\System32\OpenSSH\ssh.exe"
$key = "$env:USERPROFILE\.ssh\strato_tunnel_pc"
$log = "$env:LOCALAPPDATA\strato-tunnel-pc.log"

while ($true) {
    "$(Get-Date -Format s) Tunnel startet" | Add-Content $log
    & $ssh -N `
        -o ExitOnForwardFailure=yes `
        -o ServerAliveInterval=15 `
        -o ServerAliveCountMax=3 `
        -o StrictHostKeyChecking=accept-new `
        -o BatchMode=yes `
        -i $key `
        -R 18331:127.0.0.1:11434 `
        tunnel@82.165.153.177 2>&1 | Add-Content $log
    "$(Get-Date -Format s) Tunnel beendet (Exit $LASTEXITCODE), Neustart in 5 s" | Add-Content $log
    Start-Sleep -Seconds 5
}
