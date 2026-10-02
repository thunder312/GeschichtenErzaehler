# PC — zweiter KI-Host (NVIDIA-GPU) für Geschichten Erzähler

Neben Athene (CPU, siehe `athene/README.md`) kann der Windows-PC die Text-KI
rechnen. Mit der **RTX 5070 Ti (16 GB VRAM)** passt der Autor
(`mistral-small3.2`, 24B q4) fast oder ganz auf die GPU und ist damit grob
10–15× schneller als auf Athene. Die Prüfer (`gemma4`) passen bequem.

**Stand:** vorbereitet, aber noch nicht eingerichtet (die Karte ist noch nicht
eingebaut). Nichts hiervon ist auf Strato oder Prod aktiv.

| Umgebung | wie der PC erreicht wird |
|---|---|
| Dev (dieser PC) | KI-Ziel `PC (lokal)`, Typ `direct`, Host `http://127.0.0.1:11434` |
| Prod (Strato) | **Reverse-SSH-Tunnel** PC → Strato; KI-Ziel `PC (Tunnel)`, Typ `direct`, Host `http://127.0.0.1:18331` |

**Umschalten** im Kopfbereich (bei geöffnetem Projekt): ein Knopf pro KI-Ziel,
z.B. `Athene` (langsam, läuft immer — Automatik über Nacht) ↔ `PC` (schnell,
muss laufen). Der Punkt zeigt grün/rot, ob das Ziel gerade erreichbar ist
(geprüft beim Laden und beim Anklicken). Die Wahl merkt sich der Browser.
Ein schon laufender Automatik-Lauf bleibt auf dem Ziel, mit dem er gestartet
wurde.

Ein Lauf (Schreiben, Automatik, Prüfen) nutzt immer **ein** KI-Ziel für alle
Rollen. Autor auf dem PC und Prüfer auf Athene gleichzeitig geht (noch) nicht.
Der PC muss laufen, solange mit dem Ziel `PC (Tunnel)` geschrieben wird.

## Dateien

| Datei | Zweck |
|---|---|
| `ollama-compose.yaml` | Ollama-Container mit NVIDIA-GPU (Docker Desktop) |
| `strato-tunnel.ps1` | Reverse-Tunnel-Schleife, gestartet per Aufgabenplanung |

## Einrichten (nach dem Kartentausch)

### 1. Ollama

```bash
cd pc
docker compose -f ollama-compose.yaml up -d
docker exec ollama ollama pull mistral-small3.2
docker exec ollama ollama pull gemma4
```

Prüfen, ob die GPU genutzt wird: ein kurzer Prompt, dann `docker exec ollama
ollama ps`. Die Spalte `PROCESSOR` sollte `100% GPU` zeigen (bei Mistral mit
16k Kontext evtl. `9x%/x%`, das ist ok).

**Geteilte GPU:** Bild-KIs (`D:\KI-Server\Dienste\bild-kis.16gb.yaml`) und
Ollama passen nicht gleichzeitig in 16 GB. `OLLAMA_KEEP_ALIVE=10m` gibt den
VRAM nach 10 Minuten Pause frei; sofort geht es mit
`docker exec ollama ollama stop mistral-small3.2:latest`. Vor dem Schreiben
laufende Bild-KIs stoppen (`docker stop sd-server-dev` usw.).

### 2. Lokales KI-Ziel (Dev)

Im Tab „KI-Ziele": neues Ziel `PC (lokal)`, Auth-Methode `direct`, Host
`http://127.0.0.1:11434`, „Verbindung testen". Steuer- und Bild-Ports leer
lassen; die „KI- und Speicherkontrolle" wird für dieses Ziel dann übersprungen.

### 3. Reverse-Tunnel für Prod

**a) Schlüssel erzeugen** (PowerShell):
```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\strato_tunnel_pc -N '""' -C "pc-tunnel"
Get-Content $env:USERPROFILE\.ssh\strato_tunnel_pc.pub
```

**b) Strato** (per SSH als Admin):
1. Public Key an `/home/tunnel/.ssh/authorized_keys` anhängen.
2. In `/etc/ssh/sshd_config` im `Match User tunnel`-Block
   `localhost:18331` zur `PermitOpen`-Zeile ergänzen (bestehende Ports von
   Athene 18321–18324 stehen lassen!), dann
   `sudo sshd -t && sudo systemctl reload ssh`.

**c) Test von Hand:**
```powershell
powershell -ExecutionPolicy Bypass -File pc\strato-tunnel.ps1
```
Auf Strato: `curl -s http://127.0.0.1:18331/api/tags` muss die Modell-Liste
liefern. Log: `%LOCALAPPDATA%\strato-tunnel-pc.log`.

**d) Dauerhaft per Aufgabenplanung** (PowerShell als Admin, Pfad anpassen
falls das Repo woanders liegt):
```powershell
$skript = "D:\Dropbox\Entwicklung\GeschichtenErzähler\pc\strato-tunnel.ps1"
$aktion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$skript`""
$ausloeser = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$einst = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName "Strato-Tunnel PC" -Action $aktion `
    -Trigger $ausloeser -Settings $einst
```
Entfernen: `Unregister-ScheduledTask -TaskName "Strato-Tunnel PC"`.

**e) Prod:** im Tab „KI-Ziele" neues Ziel `PC (Tunnel)`, Auth-Methode
`direct`, Host `http://127.0.0.1:18331`, testen. Beim Schreiben dieses Ziel
statt `Athene (Tunnel)` wählen.

## Troubleshooting

**`ollama ps` zeigt viel `CPU`** → eine Bild-KI belegt den VRAM
(`nvidia-smi`), oder der Kontext ist größer als gedacht.

**Tunnel startet ständig neu** → Log ansehen. `remote port forwarding
failed` = `PermitOpen localhost:18331` fehlt auf Strato; `Permission denied`
= Key nicht in `authorized_keys`.

**Antworten auf Prod sehr langsam, obwohl `100% GPU`** → Upload-Bandbreite
des Heimanschlusses prüfen; die Tokens laufen über den Tunnel, das ist aber
normalerweise unkritisch.
