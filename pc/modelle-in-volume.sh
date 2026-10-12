#!/bin/bash
# Verschiebt den Ollama-Modellspeicher vom Windows-Ordner (D:\KI-Server\Modelle\
# ollama, per 9p/drvfs eingehängt, msize 64 KB -> langsam) in ein Docker-Volume
# (ext4 innerhalb der Docker-VM, liegt in C:\DockerData\DockerDesktopWSL\disk\
# docker_data.vhdx). Grund: pro Kapitel lädt Ollama zweimal ein Modell um
# (Mistral <-> gemma4), und das Laden dauert über 9p 70-100 s.
#
# Aufruf (nacheinander, am besten wenn KEIN Schreiblauf läuft):
#   ! ./pc/modelle-in-volume.sh messen [modell]   Ladezeit VORHER messen
#   ! ./pc/modelle-in-volume.sh kopieren          Modelle ins Volume kopieren (~5-10 min)
#   ! ./pc/modelle-in-volume.sh umstellen         Compose auf das Volume umstellen + neu starten
#   ! ./pc/modelle-in-volume.sh messen [modell]   Ladezeit NACHHER messen
#   ! ./pc/modelle-in-volume.sh zurueck           Notausgang: wieder auf den D:-Ordner
# Der D:-Ordner bleibt unangetastet (= Sicherung) - erst löschen, wenn alles läuft.
# FORCE=1 überspringt die Prüfung "es läuft gerade ein Lauf".

set -euo pipefail
# Git Bash würde sonst "/quelle" in einen Windows-Pfad umschreiben (docker run -v ...).
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"

COMPOSE="ollama-compose.yaml"
SICHERUNG="ollama-compose.yaml.bak-bindmount"
VOLUME="ge-ollama-modelle"
QUELLE="D:/KI-Server/Modelle/ollama"
API="http://127.0.0.1:11434"

fehler() { echo "FEHLER: $*" >&2; exit 1; }
info()   { echo "== $*"; }

docker info >/dev/null 2>&1 || fehler "Docker läuft nicht."

ollama_beschaeftigt() {
  # Ein geladenes Modell oder GPU-Last deuten auf einen laufenden Lauf hin.
  local ps gpu
  ps=$(docker exec ollama ollama ps 2>/dev/null | tail -n +2 | grep -c . || true)
  gpu=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1 || echo 0)
  [ "${ps:-0}" -gt 0 ] || [ "${gpu:-0}" -gt 20 ]
}

nicht_waehrend_lauf() {
  if [ "${FORCE:-0}" != "1" ] && ollama_beschaeftigt; then
    fehler "Ollama hat gerade ein Modell geladen oder die GPU rechnet - läuft ein Schreiblauf? (FORCE=1 überspringt das)"
  fi
}

warten_auf_ollama() {
  for _ in $(seq 1 60); do
    # Kein "-o /dev/null": mit MSYS_NO_PATHCONV=1 kann das Windows-curl den Pfad nicht
    # schreiben und meldet trotz HTTP 200 einen Fehler (Exit 23).
    curl -s -m 3 "$API/api/tags" >/dev/null && return 0
    sleep 2
  done
  fehler "Ollama antwortet nach 2 Minuten nicht."
}

cmd_messen() {
  local modell="${1:-gemma4:latest}"
  nicht_waehrend_lauf
  info "Kaltstart-Messung für $modell"
  docker exec ollama ollama stop "$modell" >/dev/null 2>&1 || true
  # Dateicache der Docker-VM leeren, sonst misst man den Cache statt der Platte.
  wsl.exe -d docker-desktop -e sh -c "sync; echo 3 > /proc/sys/vm/drop_caches" 2>/dev/null \
    && info "Cache der Docker-VM geleert" || echo "   (Cache konnte nicht geleert werden - Wert kann zu gut sein)"
  local antwort
  # Ein LEERER Prompt mit keep_alive 0 ENTLÄDT bei Ollama nur - zum Messen braucht es
  # einen echten (winzigen) Prompt; danach wieder entladen.
  antwort=$(curl -s -m 600 "$API/api/generate" \
    -d "{\"model\":\"$modell\",\"prompt\":\"Hallo\",\"stream\":false,\"options\":{\"num_predict\":1}}")
  docker exec ollama ollama stop "$modell" >/dev/null 2>&1 || true
  local ns
  ns=$(echo "$antwort" | python -I -c 'import sys,json; print(json.load(sys.stdin).get("load_duration",0))')
  python -I -c "print('   Ladezeit $modell: %.1f s' % ($ns/1e9))"
  echo "   Speicherort jetzt: $(docker inspect ollama --format '{{range .Mounts}}{{.Type}}:{{.Name}}{{.Source}}{{end}}')"
}

cmd_kopieren() {
  nicht_waehrend_lauf
  [ -d "/d/KI-Server/Modelle/ollama" ] || fehler "Quelle $QUELLE nicht gefunden."
  info "Lege Volume $VOLUME an (falls nötig)"
  docker volume create "$VOLUME" >/dev/null
  info "Kopiere Modelle ($(du -sh /d/KI-Server/Modelle/ollama | cut -f1)) - das dauert einige Minuten ..."
  docker run --rm -v "$QUELLE:/quelle:ro" -v "$VOLUME:/ziel" alpine \
    sh -c 'cp -a /quelle/. /ziel/ && sync'
  cmd_pruefen
}

cmd_pruefen() {
  info "Prüfe die Kopie (Dateianzahl und Summe der Dateigrößen)"
  local a b
  # Nur Dateien zählen: "du -sb" rechnet die Verzeichniseinträge mit, und die sind auf
  # 9p (D:) und ext4 (Volume) verschieden groß - das gab einen falschen Alarm.
  local zaehlen='find /x -type f | wc -l; find /x -type f -exec stat -c %s {} + | awk "{s+=\$1} END{print s}"'
  a=$(docker run --rm -v "$QUELLE:/x:ro" alpine sh -c "$zaehlen" | tr '\n' ' ')
  b=$(docker run --rm -v "$VOLUME:/x:ro" alpine sh -c "$zaehlen" | tr '\n' ' ')
  echo "   Quelle (D:): $a"
  echo "   Volume:      $b"
  [ "$a" = "$b" ] || fehler "Quelle und Volume unterscheiden sich - NICHT umstellen, 'kopieren' wiederholen."
  echo "   OK: identisch."
}

cmd_umstellen() {
  nicht_waehrend_lauf
  grep -q "$VOLUME" "$COMPOSE" && fehler "$COMPOSE nutzt das Volume schon."
  cmd_pruefen
  info "Sichere $COMPOSE als $SICHERUNG"
  cp "$COMPOSE" "$SICHERUNG"
  # Bind-Mount durch das (externe) Volume ersetzen + Volume-Deklaration anhängen
  sed -i "s#- D:/KI-Server/Modelle/ollama:/root/.ollama#- $VOLUME:/root/.ollama#" "$COMPOSE"
  grep -q "$VOLUME:/root/.ollama" "$COMPOSE" || { cp "$SICHERUNG" "$COMPOSE"; fehler "Bind-Mount-Zeile nicht gefunden, Compose unverändert."; }
  printf '\nvolumes:\n  %s:\n    external: true\n' "$VOLUME" >> "$COMPOSE"
  info "Starte Ollama mit dem Volume neu"
  docker compose -f "$COMPOSE" up -d --force-recreate
  warten_auf_ollama
  echo "   Modelle im neuen Speicher:"
  docker exec ollama ollama list
  info "Fertig. Jetzt 'messen' wiederholen und mit dem VORHER-Wert vergleichen."
}

cmd_zurueck() {
  nicht_waehrend_lauf
  [ -f "$SICHERUNG" ] || fehler "Keine Sicherung $SICHERUNG gefunden."
  cp "$SICHERUNG" "$COMPOSE"
  docker compose -f "$COMPOSE" up -d --force-recreate
  warten_auf_ollama
  info "Zurück auf den D:-Ordner:"
  docker exec ollama ollama list
}

case "${1:-}" in
  messen)    shift; cmd_messen "$@" ;;
  kopieren)  cmd_kopieren ;;
  pruefen)   cmd_pruefen ;;
  umstellen) cmd_umstellen ;;
  zurueck)   cmd_zurueck ;;
  *) sed -n 12,20p "$0"; exit 1 ;;
esac
