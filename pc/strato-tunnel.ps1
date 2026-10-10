# Reverse-SSH-Tunnel PC -> Strato, damit Prod (geschichten.daniel-ertl.de)
# das Ollama auf diesem PC nutzen kann. Gegenstück zu
# athene/systemd/strato-tunnel.service; Windows hat kein systemd, daher
# eine Endlosschleife, die per Aufgabenplanung bei der Anmeldung startet
# (Einrichtung siehe pc/README.md).
#
# Port-Zuordnung:  Strato 127.0.0.1:18331  ->  PC 127.0.0.1:11434 (Ollama)
#                  Strato 127.0.0.1:18332  ->  PC 127.0.0.1:7862  (Steuer-Dienst,
#                  "KI starten & Modelle scannen", siehe pc/steuerung-dienst.ps1)
# Beide Ports MÜSSEN auf Strato im "Match User tunnel"-Block bei PermitOpen
# stehen, sonst bricht der Tunnel wegen ExitOnForwardFailure sofort ab. Fehlt
# nur 18332, fällt das Skript nach dem ersten Fehlschlag auf den reinen
# Ollama-Tunnel zurück (Log: "ohne Steuer-Dienst"), damit die KI weiter geht.

$ssh = "$env:SystemRoot\System32\OpenSSH\ssh.exe"
$key = "$env:USERPROFILE\.ssh\strato_tunnel_pc"
$log = "$env:LOCALAPPDATA\strato-tunnel-pc.log"

$mitSteuerung = $true

while ($true) {
    $weiterleitungen = @("-R", "18331:127.0.0.1:11434")
    if ($mitSteuerung) { $weiterleitungen += @("-R", "18332:127.0.0.1:7862") }
    "$(Get-Date -Format s) Tunnel startet" + $(if ($mitSteuerung) { "" } else { " (ohne Steuer-Dienst)" }) | Add-Content $log
    $start = Get-Date
    $zeilen = @(& $ssh -N `
        -o ExitOnForwardFailure=yes `
        -o ServerAliveInterval=15 `
        -o ServerAliveCountMax=3 `
        -o StrictHostKeyChecking=accept-new `
        -o BatchMode=yes `
        -i $key `
        @weiterleitungen `
        tunnel@82.165.153.177 2>&1)
    $zeilen | Add-Content $log
    # Schlug sofort ein Port-Forwarding fehl, fehlt auf Strato vermutlich
    # PermitOpen für 18332 -> ab jetzt nur noch Ollama weiterleiten.
    if ($mitSteuerung -and ((Get-Date) - $start).TotalSeconds -lt 20 -and ($zeilen -match "forwarding failed")) {
        $mitSteuerung = $false
        "$(Get-Date -Format s) Port 18332 abgelehnt (PermitOpen auf Strato fehlt?) - weiter ohne Steuer-Dienst" | Add-Content $log
    }
    "$(Get-Date -Format s) Tunnel beendet (Exit $LASTEXITCODE), Neustart in 5 s" | Add-Content $log
    Start-Sleep -Seconds 5
}
