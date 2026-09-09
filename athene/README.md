# Athene — KI-Host für Geschichten Erzähler

Athene ist der Linux-Rechner, auf dem die KI-Modelle laufen. Die App (lokal
*und* Prod auf `geschichten.daniel-ertl.de`) spricht ihn als **KI-Ziel** an:

| Umgebung | wie Athene erreicht wird |
|---|---|
| Dev (Windows) | direktes SSH-Ziel im LAN (`192.168.188.181`, User `daniel`) — Tab „KI-Ziele" |
| Prod (Strato) | **Reverse-SSH-Tunnel** Athene → Strato; App-KI-Ziel `Athene (Tunnel)` vom Typ `direct` (`http://127.0.0.1:1832x`) |

Athene wählt sich bei Strato ein (Router bleibt zu, keine Portfreigabe, keine
feste IP nötig).

## Hardware (Stand 2026-09)

- AMD Ryzen APU, **16 Kerne**, **30 GB RAM**, ~7 GB Swap
- **AMD Radeon 780M** (gfx1103, „HawkPoint") — integrierte GPU, **kein eigener
  VRAM**, teilt sich den System-RAM (UMA). **Keine dedizierte GPU.**
- Ubuntu 26.04 LTS, Docker 29, Docker Compose v5
- GPU-Nutzung ausschließlich über **Vulkan**, nicht ROCm (ROCm ist auf gfx1103
  instabil — Ollama-Runner stürzt ab).

## Was auf Athene läuft (für dieses Projekt)

| Container | Image | Port | Zweck |
|---|---|---|---|
| `ollama` | `ollama/ollama` | 11434 | Text-KI (Autor, Prüfer, Architekt …) |
| `sd-server` | `sd-vulkan` (lokal gebaut) | 7860 | Titelbild — FLUX.1-schnell |
| `sd-server-pony` | `sd-vulkan` | 7861 | Titelbild — Pony V6 XL + ControlNet + IP-Adapter |
| `athene-steuerung` | venv-Dienst | 7862 | RAM/Swap-Status + Container start/stop (Feature „KI- und Speicherkontrolle") |

systemd: **`strato-tunnel.service`** (Reverse-Tunnel), **`athene-steuerung.service`**.
Die native `ollama.service` ist bewusst `disable`d — es läuft nur der Container.

> Nicht Teil dieses Projekts (laufen auf Athene, aber unabhängig): `frigate`,
> `videobuddy`, `open-webui`, `portainer`.

## Modelle

**Ollama** (`~/ollama/models`, gemountet als `/usr/share/ollama`):
- `gemma4` — Prüfer, Architekt, Chronist, Cover-Prompt (Preview-Modell; falls
  nicht `pull`-bar, im Tab „KI-Ziele" die Persona-Zuordnung auf `gemma3`/o.ä. ändern)
- `mistral-small3.2:latest` (24B q4) — Autor

**FLUX** (`~/sd-test/models`):
`flux1-schnell-Q4_K_S.gguf`, `clip_l.safetensors`, `t5xxl-Q5_K_M.gguf` (**GGUF**,
nicht `.safetensors` — sonst lädt sd.cpp den T5 als f16 = ~9 GB RAM = Swap voll),
`ae.safetensors`.

**Pony** (`~/sd-test/models-pony`):
`pony-diffusion-v6-xl-Q8_0.gguf`, `loras/Realism Lora By Stable Yogi_V3_Lite.safetensors`
(Civitai, Token nötig), `controlnet/controlnet-canny-sdxl.safetensors`,
`ipadapter/ip-adapter_sdxl_vit-h.safetensors` (+ `-plus-face`),
`clip_vision/clip_vision_vit_h.safetensors` (+ `config.json`).

Quellen und exakte URLs: `modelle-holen.sh`.

## Neu aufsetzen

Dieses Verzeichnis auf den Rechner kopieren, dann:

```bash
cd athene
./setup.sh check       # Voraussetzungen (docker, /dev/dri, Gruppen video+docker)
./setup.sh image       # baut sd-vulkan aus leejet/stable-diffusion.cpp (Dockerfile.vulkan)
./setup.sh compose     # startet ollama + sd-server + sd-server-pony
./setup.sh models      # zieht Ollama-Modelle + lädt alle SD-Modelle
./setup.sh steuerung   # installiert athene-steuerung.service, gibt den Token aus
./setup.sh tunnel      # interaktiv: Key erzeugen, Strato-Schritte anzeigen, Dienst starten
# oder in einem:
CIVITAI_TOKEN=xxxx ./setup.sh all      # alles außer 'tunnel'
```

### Der Reverse-Tunnel (Strato-Seite, einmalig)

`./setup.sh tunnel` erzeugt `~/.ssh/strato_tunnel` und zeigt an, was auf Strato
zu tun ist:

1. Public Key in `/home/tunnel/.ssh/authorized_keys` eintragen (User `tunnel`
   existiert dort, Home `/home/tunnel`).
2. In `/etc/ssh/sshd_config` den `Match User tunnel`-Block mit
   `PermitOpen localhost:18321…18324` sicherstellen, dann `sudo sshd -t &&
   sudo systemctl reload ssh`. **Jeder neue `-R`-Port braucht eine
   `PermitOpen`-Zeile** — sonst scheitert der ganze Tunnel (`ExitOnForwardFailure`).
3. Auf Prod im Tab „KI-Ziele" das Ziel `Athene (Tunnel)` prüfen: `auth_method
   direct`, Host `http://127.0.0.1:18321`, `remote_ollama_port 11434`,
   `bildki_port 18322`, `bildki_port_pony 18323`, `steuer_port 18324`.

Port-Zuordnung des Tunnels: `18321→11434` (Ollama), `18322→7860` (FLUX),
`18323→7861` (Pony), `18324→7862` (Steuerung).

## Betrieb / Troubleshooting

**Langsamer Schreib-/Automatik-Lauf gegen Athene** → fast immer voller Swap,
weil die SD-Container im Leerlauf RAM belegen, den der 24B-Autor braucht:

```bash
ssh athene "free -g; ollama ps; docker ps; ps -o pid,stat,cmd -C llama-server"
# Autor-Prozess in Status 'D' (uninterruptible sleep) + Swap 7/7  ->
docker stop sd-server sd-server-pony      # ~13 GB sofort frei
# zurück, wenn Titelbilder gebraucht werden:
docker start sd-server-pony               # bzw. sd-server
```

Das automatisiert das Feature **„KI- und Speicherkontrolle"** (siehe
`athene/steuerung/` und den Einstellungs-Schalter in der App): vor **jedem**
Start (interaktives Schreiben, Automatik, „Bestätige alles") fragt die App, ob
die nicht benötigten Bild-Container heruntergefahren werden sollen; nach einem
Automatik-Lauf bietet sie das Wiederhochfahren an. Für ein Bild mitten im
Schreiben kommt eine Performance-Warnung mit „auf eigene Gefahr".

**sd-server liefert HTTP 500 `Operation not permitted [./proc/...]`** →
`working_dir: /models` fehlt in der Compose-Datei (sd.cpp scannt sonst ab `/`).

**Pony-`capabilities` zeigt `ip_adapters: null`** → `--clip_vision` (Unterstrich!)
fehlt oder zeigt ins Leere; `--ip-adapter` braucht ihn zwingend.

**Tunnel-Dienst restartet ständig** → `journalctl -u strato-tunnel -n 50`;
meist `PermitOpen` auf Strato fehlt für einen der Ports, oder der Key ist nicht
in `authorized_keys`.
