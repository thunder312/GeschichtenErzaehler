#!/bin/bash
# Hard-Stop fuer geschichten.service: sofortiger SIGKILL, ohne Ruecksicht auf
# laufende Anfragen oder einen aktiven Automatikmodus-Lauf. Nur fuer den
# Fall, dass der normale Weg (POST /automatik/stop, kooperativ - siehe
# app/api/pipeline.py:_automatik_stop_angefordert) haengt, weil gerade ein
# LLM-Request auf einem langsamen/toten KI-Ziel offen ist.
#
# Ausfuehren als root direkt auf dem Strato-vServer:
#   /var/www/geschichten/backend/scripts/hard-stop-geschichten.sh
#
# systemd startet den Dienst danach automatisch neu (Restart=on-failure in
# /etc/systemd/system/geschichten.service). Beim Neustart raeumt
# app/main.py (verwaiste_laeufe_zuruecksetzen) eine haengengebliebene
# automatik_status.json mit "laeuft": true von selbst auf - ein
# unvollstaendig geschriebenes Kapitel bleibt aber ggf. auf der Platte
# stehen und muss manuell im Frontend geprueft werden.
set -euo pipefail

SERVICE="geschichten"
PORT=8010

echo "== Hard-Stop ${SERVICE} (Port ${PORT}) =="

echo "Sende SIGKILL an ${SERVICE}..."
systemctl kill --signal=SIGKILL "${SERVICE}" || true
sleep 1

# Fallback: normalerweise unnoetig, da ExecStart ohne --reload nur einen
# einzigen Prozess startet - falls trotzdem noch etwas auf dem Port haengt.
if ss -ltn | grep -q ":${PORT} "; then
    echo "Port ${PORT} noch belegt, kille verbleibenden Prozess per fuser..."
    fuser -k "${PORT}/tcp" || true
    sleep 1
fi

echo "Warte auf automatischen Neustart durch systemd..."
sleep 3
systemctl status "${SERVICE}" --no-pager
