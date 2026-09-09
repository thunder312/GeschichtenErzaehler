#!/usr/bin/env bash
# =============================================================================
# Athene-Setup für "Geschichten Erzähler"
# =============================================================================
# Richtet auf einem frischen Linux-Rechner (getestet: Ubuntu 26.04, AMD Ryzen
# mit Radeon 780M iGPU) alles ein, was die App als KI-Host braucht:
#   - Docker-Container: ollama (Text), sd-server (FLUX), sd-server-pony (Pony)
#   - das lokal gebaute Docker-Image `sd-vulkan` (stable-diffusion.cpp/Vulkan)
#   - alle Modell-Dateien
#   - den Reverse-SSH-Tunnel zu Strato (damit Prod die KIs erreicht)
#   - den Steuer-Dienst `athene-steuerung` (Feature "KI- und Speicherkontrolle")
#
# Idempotent — mehrfach ausführbar. Einzelschritte:
#   ./setup.sh check      Voraussetzungen prüfen (ändert nichts)
#   ./setup.sh image      sd-vulkan-Image bauen
#   ./setup.sh models     Modelle laden (Ollama + SD)
#   ./setup.sh compose    Container starten
#   ./setup.sh steuerung  Steuer-Dienst installieren
#   ./setup.sh tunnel     Reverse-Tunnel einrichten (interaktiv, Key + Strato)
#   ./setup.sh all        alles der Reihe nach (ohne tunnel — siehe README)
#
# Umgebungsvariablen (Defaults in Klammern):
#   ATHENE_USER   (der aufrufende User)   Besitzer der Dateien/Dienste
#   SDCPP_DIR     (~/sd-test/stable-diffusion.cpp)
#   SDCPP_REF     (master-812-ea7f0c8-2-gc6beeef)   git-Ref, gegen den getestet
#   FLUX_DIR      (~/sd-test/models)
#   PONY_DIR      (~/sd-test/models-pony)
#   STRATO_HOST   (82.165.153.177)
#   STRATO_TUNNEL_USER (tunnel)
#   CIVITAI_TOKEN (leer)   für die Realism-LoRA, siehe modelle-holen.sh
# =============================================================================
set -euo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ATHENE_USER="${ATHENE_USER:-$(id -un)}"
SDCPP_DIR="${SDCPP_DIR:-$HOME/sd-test/stable-diffusion.cpp}"
SDCPP_REF="${SDCPP_REF:-master-812-ea7f0c8-2-gc6beeef}"
FLUX_DIR="${FLUX_DIR:-$HOME/sd-test/models}"
PONY_DIR="${PONY_DIR:-$HOME/sd-test/models-pony}"
STRATO_HOST="${STRATO_HOST:-82.165.153.177}"
STRATO_TUNNEL_USER="${STRATO_TUNNEL_USER:-tunnel}"

log()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!  %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mFEHLER: %s\033[0m\n' "$*" >&2; exit 1; }

# -----------------------------------------------------------------------------
cmd_check() {
  log "Voraussetzungen"
  command -v docker >/dev/null || die "docker fehlt — https://docs.docker.com/engine/install/"
  docker compose version >/dev/null 2>&1 || die "docker compose (v2) fehlt"
  [[ -e /dev/dri ]] || die "/dev/dri fehlt — keine GPU/iGPU sichtbar"
  id -nG "$ATHENE_USER" | grep -qw video || warn "User '$ATHENE_USER' ist nicht in Gruppe 'video' (für iGPU-Zugriff): sudo usermod -aG video $ATHENE_USER; neu einloggen"
  id -nG "$ATHENE_USER" | grep -qw docker || warn "User '$ATHENE_USER' ist nicht in Gruppe 'docker'"
  command -v git >/dev/null   || die "git fehlt"
  command -v wget >/dev/null  || die "wget fehlt"
  lspci 2>/dev/null | grep -iE 'vga|display' | grep -qi amd && echo "  AMD-GPU erkannt (Vulkan-Backend)" || warn "keine AMD-GPU per lspci gefunden — Vulkan-Setup ggf. anpassen"
  echo "  ok"
}

# -----------------------------------------------------------------------------
cmd_image() {
  log "Docker-Image sd-vulkan bauen"
  if docker image inspect sd-vulkan >/dev/null 2>&1; then
    echo "  sd-vulkan existiert bereits — überspringe (docker rmi sd-vulkan erzwingt Neubau)"
    return
  fi
  if [[ ! -d "$SDCPP_DIR/.git" ]]; then
    mkdir -p "$(dirname "$SDCPP_DIR")"
    git clone --recursive https://github.com/leejet/stable-diffusion.cpp "$SDCPP_DIR"
  fi
  ( cd "$SDCPP_DIR"
    git fetch --tags origin
    git checkout "$SDCPP_REF" 2>/dev/null || warn "git-Ref '$SDCPP_REF' nicht gefunden — bleibe auf $(git rev-parse --short HEAD)"
    git submodule update --init --recursive
    docker build -f docker/Dockerfile.vulkan -t sd-vulkan .
  )
  echo "  sd-vulkan gebaut"
}

# -----------------------------------------------------------------------------
cmd_models() {
  log "Ollama-Modelle"
  docker ps --format '{{.Names}}' | grep -qx ollama || die "ollama-Container läuft nicht — erst './setup.sh compose'"
  for m in gemma4 mistral-small3.2; do
    if docker exec ollama ollama list | grep -q "^${m}"; then
      echo "  ok    $m"
    else
      echo "  pull  $m"
      docker exec ollama ollama pull "$m" || warn "'$m' konnte nicht gepullt werden — im Tab 'KI-Ziele' die Persona-Modell-Zuordnung anpassen"
    fi
  done

  log "SD-Modelle"
  CIVITAI_TOKEN="${CIVITAI_TOKEN:-}" FLUX_DIR="$FLUX_DIR" PONY_DIR="$PONY_DIR" bash "$HIER/modelle-holen.sh" all
}

# -----------------------------------------------------------------------------
cmd_compose() {
  log "Container starten"
  mkdir -p "$FLUX_DIR" "$PONY_DIR/loras" "$PONY_DIR/controlnet" "$PONY_DIR/ipadapter" "$PONY_DIR/clip_vision"
  mkdir -p "$HOME/.ollama" "$HOME/ollama/models"
  docker image inspect sd-vulkan >/dev/null 2>&1 || die "Image sd-vulkan fehlt — erst './setup.sh image'"
  docker compose -f "$HIER/compose/ollama-compose.yaml"         up -d
  docker compose -f "$HIER/compose/sd-server-compose.yaml"      up -d
  docker compose -f "$HIER/compose/sd-server-pony-compose.yaml" up -d
  echo "  Container:"; docker ps --format '   {{.Names}}\t{{.Status}}\t{{.Ports}}'
  warn "Die native ollama.service ggf. deaktivieren, damit sie nicht mit dem Container um Port 11434 kämpft:  sudo systemctl disable --now ollama.service"
}

# -----------------------------------------------------------------------------
cmd_steuerung() {
  log "Steuer-Dienst athene-steuerung"
  command -v python3 >/dev/null || die "python3 fehlt"
  local dst="$HOME/athene-steuerung"
  mkdir -p "$dst"
  cp "$HIER/steuerung/app.py" "$dst/"

  local tokfile="$dst/token"
  if [[ ! -f "$tokfile" ]]; then
    head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40 > "$tokfile"
    chmod 600 "$tokfile"
    echo "  neuer Token erzeugt: $tokfile"
  fi
  echo
  echo "  >>> Diesen Token im App-Tab 'KI-Ziele' beim Ziel 'Athene (Tunnel)' als Steuer-Token hinterlegen:"
  echo "  >>> $(cat "$tokfile")"
  echo

  sudo cp "$HIER/systemd/athene-steuerung.service" /etc/systemd/system/athene-steuerung.service
  sudo sed -i "s|__USER__|$ATHENE_USER|g; s|__DIR__|$dst|g" /etc/systemd/system/athene-steuerung.service
  # Der Dienst darf `docker` aufrufen -> User muss in der docker-Gruppe sein.
  sudo systemctl daemon-reload
  sudo systemctl enable --now athene-steuerung.service
  sleep 1
  curl -sS -H "Authorization: Bearer $(cat "$tokfile")" http://127.0.0.1:7862/status | head -c 400 || true
  echo
  systemctl is-active athene-steuerung.service || true
  echo "  Port 7862 (Reverse-Tunnel 18324, siehe './setup.sh tunnel')"
}

# -----------------------------------------------------------------------------
cmd_tunnel() {
  log "Reverse-SSH-Tunnel zu Strato"
  local key="$HOME/.ssh/strato_tunnel"
  if [[ ! -f "$key" ]]; then
    ssh-keygen -t ed25519 -N '' -C 'athene-reverse-tunnel' -f "$key"
  fi
  echo
  echo "  1) Diesen Public Key auf Strato in /home/$STRATO_TUNNEL_USER/.ssh/authorized_keys eintragen:"
  echo "     ---8<---"; cat "$key.pub"; echo "     --->8---"
  echo
  echo "  2) Auf Strato in /etc/ssh/sshd_config den Block sicherstellen (dann: sudo sshd -t && sudo systemctl reload ssh):"
  cat <<EOF
     Match User $STRATO_TUNNEL_USER
         PasswordAuthentication no
         AllowTcpForwarding remote
         PermitOpen localhost:18321
         PermitOpen localhost:18322
         PermitOpen localhost:18323
         PermitOpen localhost:18324
         X11Forwarding no
         PermitTTY no
         ForceCommand /bin/false
         GatewayPorts no
EOF
  echo
  read -r -p "  Beide Schritte auf Strato erledigt? Tunnel-Dienst jetzt installieren? [j/N] " a
  [[ "$a" == "j" || "$a" == "J" ]] || { warn "abgebrochen"; return; }
  sudo cp "$HIER/systemd/strato-tunnel.service" /etc/systemd/system/strato-tunnel.service
  sudo sed -i "s|User=daniel|User=$ATHENE_USER|; s|/home/daniel/.ssh/strato_tunnel|$key|; s|tunnel@82.165.153.177|$STRATO_TUNNEL_USER@$STRATO_HOST|" /etc/systemd/system/strato-tunnel.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now strato-tunnel.service
  sleep 3
  systemctl --no-pager status strato-tunnel.service | head -12
}

# -----------------------------------------------------------------------------
case "${1:-all}" in
  check)     cmd_check ;;
  image)     cmd_check; cmd_image ;;
  models)    cmd_models ;;
  compose)   cmd_check; cmd_compose ;;
  steuerung) cmd_steuerung ;;
  tunnel)    cmd_tunnel ;;
  all)       cmd_check; cmd_image; cmd_compose; cmd_models; cmd_steuerung
             echo; warn "Reverse-Tunnel separat: ./setup.sh tunnel  (braucht Strato-Zugriff)" ;;
  *) echo "Aufruf: $0 [check|image|models|compose|steuerung|tunnel|all]"; exit 1 ;;
esac
