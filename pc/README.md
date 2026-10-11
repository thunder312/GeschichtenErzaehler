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
| `strato-tunnel.ps1` | Reverse-Tunnel-Schleife (Ollama :18331, Steuer-Dienst :18332), gestartet per Aufgabenplanung |
| `steuerung-dienst.ps1` / `steuerung-einrichten.ps1` | Steuer-Dienst für den Knopf „KI starten & Modelle scannen“ |
| `modelle-in-volume.sh` | Modellspeicher von D:\ in ein Docker-Volume verschieben (schnelleres Laden) |
| `tunnel-aufgaben-einrichten.ps1` | Tunnel-Aufgabe + Wächter (alle 5 Min. Neustart, falls der Tunnel tot ist) |

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

## Knopf „KI starten & Modelle scannen“ (Steuer-Dienst)

In den Einstellungen gibt es pro KI-Ziel (Tab „KI-Ziele“ und bei der
„Persona-Modell-Zuordnung“) den Knopf **🚀 KI starten & Modelle scannen**. Er
prüft, ob Ollama antwortet; wenn nicht, startet er (über den Steuer-Dienst auf
dem Zielrechner) Docker Desktop und den Container `ollama`, wartet auf die API
und liest die installierten Modelle aus. Fehlen Modelle, die die Personas auf
diesem Ziel brauchen, steht das darunter. Ohne Docker selbst anzufassen.

**Grenze:** Die App erreicht den PC nur über den Reverse-Tunnel. Ist der PC aus
oder der Tunnel nicht aktiv, hilft der Knopf nicht (roter Punkt im Kopfbereich).
Er deckt „Tunnel steht, aber Docker/Ollama sind aus“ ab.

Einrichten (einmalig, in dieser Reihenfolge):

1. **Strato:** in `/etc/ssh/sshd_config` im `Match User tunnel`-Block
   `localhost:18332` zur `PermitOpen`-Zeile ergänzen (18331 und 18321–18324
   stehen lassen), dann `sudo sshd -t && sudo systemctl reload ssh`.
2. **PC:** `! ./pc/steuerung-einrichten.sh` — legt Token + Aufgabe „Steuerung PC“
   an, startet den Dienst (`127.0.0.1:7862`) und gibt den Token aus.
3. **Tunnel neu starten**, damit er :18332 mitnimmt:
   `Stop-ScheduledTask "Strato-Tunnel PC"; Start-ScheduledTask "Strato-Tunnel PC"`
   (Log `%LOCALAPPDATA%\strato-tunnel-pc.log`; steht dort „ohne Steuer-Dienst“,
   fehlt Schritt 1).
4. **App (Prod):** Tab „KI-Ziele“ → `PC (Tunnel)` bearbeiten → Steuer-Port
   `18332`, Steuer-Token aus Schritt 2 → Aktualisieren.

Der Dienst ist `athene/steuerung/app.py` (dasselbe Programm wie auf Athene);
Log: `%LOCALAPPDATA%\ge-steuerung\steuerung.log`. Er darf nur den Container
`ollama` steuern (Whitelist in `steuerung-dienst.ps1`).

**Athene:** der Knopf funktioniert dort schon für „Ollama scannen“. Damit er
auch den Container `ollama` starten darf, `ollama` in
`STEUERBARE_CONTAINER` der `athene-steuerung.service` aufnehmen (steht jetzt in
`athene/systemd/athene-steuerung.service`) und den Dienst neu starten.

## Modellspeicher in ein Docker-Volume verschieben (schnelleres Laden)

Pro Kapitel lädt Ollama zweimal ein Modell um (Autor Mistral ↔ Prüfer gemma4,
beide zusammen passen nicht in 16 GB). Liegen die Modelle im Windows-Ordner
`D:\KI-Server\Modelle\ollama`, werden sie über 9p/drvfs (`msize=65536`)
gelesen, das Laden dauert dann 70–100 s. In einem Docker-Volume (ext4 in der
Docker-VM, liegt in `D:\KI-Server\Docker\Daten\disk\docker_data.vhdx`) sollte
es deutlich schneller gehen. Das Skript `modelle-in-volume.sh` macht den Umzug
in Schritten und lässt den D:-Ordner als Sicherung stehen:

```
! ./pc/modelle-in-volume.sh messen hf.co/bartowski/mistralai_Mistral-Small-3.2-24B-Instruct-2506-GGUF:IQ4_XS   # VORHER
! ./pc/modelle-in-volume.sh kopieren     # ~33 GB, einige Minuten, prüft die Kopie
! ./pc/modelle-in-volume.sh umstellen    # Compose auf das Volume, Ollama neu starten
! ./pc/modelle-in-volume.sh messen hf.co/bartowski/mistralai_Mistral-Small-3.2-24B-Instruct-2506-GGUF:IQ4_XS   # NACHHER
! ./pc/modelle-in-volume.sh zurueck      # Notausgang
```

Nur starten, wenn **kein** Schreiblauf auf dem PC läuft (das Skript bricht ab,
wenn ein Modell geladen ist oder die GPU rechnet; `FORCE=1` überspringt das).
Platzbedarf: das Volume wächst die `docker_data.vhdx` um ~33 GB; der D:-Ordner
bleibt bestehen, bis du ihn selbst löschst. Die vhdx schrumpft nicht von allein.

## Troubleshooting

**`ollama ps` zeigt viel `CPU`** → eine Bild-KI belegt den VRAM
(`nvidia-smi`), oder der Kontext ist größer als gedacht.

**Tunnel startet ständig neu** → Log ansehen. `remote port forwarding
failed` = `PermitOpen localhost:18331` fehlt auf Strato; `Permission denied`
= Key nicht in `authorized_keys`.

**Antworten auf Prod sehr langsam, obwohl `100% GPU`** → Upload-Bandbreite
des Heimanschlusses prüfen; die Tokens laufen über den Tunnel, das ist aber
normalerweise unkritisch.
