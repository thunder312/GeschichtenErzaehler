#!/usr/bin/env bash
# Einmalige Nachruestung auf dem Strato-Server: bringt die neue "Funktion im
# Spannungsbogen"-Erklaerung (siehe backend/app/core/epoche.py, seit
# 2026-08-24 in jeder neu erzeugten Persona enthalten) BEIDES:
#   1. in die Epochen-Bibliothek (backend/app/data) - Vorlage fuer NEUE
#      Geschichten. Wird normalerweise NICHT per deploy-all.sh mitgeschickt
#      (app/data ist dort bewusst ausgeschlossen, siehe Kommentar dort), hier
#      wird deshalb gezielt nur das eine Migrationsskript hochgeladen.
#   2. in JEDE bereits angelegte Geschichte (backend/instance/projects/.../
#      personas/) - deren Persona-Kopie wurde beim Anlegen einmalig aus der
#      Epochen-Bibliothek kopiert und aendert sich seither nie von selbst.
#
# Nutzt dafuer backend/scripts/patch_spannungsbogen_persona.py (idempotent,
# lokal bereits gegen die eigenen Vorher/Nachher-Stände verifiziert - siehe
# Session vom 2026-08-24). Ohne --apply macht dieses Skript NUR einen
# Dry-Run auf dem Server und zeigt, was sich aendern wuerde, OHNE etwas zu
# schreiben. Erst mit --apply wird tatsaechlich geschrieben.
#
# Aufruf (User fuehrt das selbst per "! ./deploy-spannungsbogen-persona.sh"
# aus, siehe [[deploy-classifier-blockiert-scp]] - Uploads zu diesem Server
# blockiert der Auto-Mode-Classifier auch nach Freigabe):
#   ./deploy-spannungsbogen-persona.sh            # Dry-Run auf dem Server
#   ./deploy-spannungsbogen-persona.sh --apply     # tatsaechlich schreiben
set -e
cd "$(dirname "$0")"

KEY="$HOME/.ssh/strato_key"
HOST="root@82.165.153.177"
REMOTE="/var/www/geschichten"
APPLY="${1:-}"

echo "============================================"
echo "0/3: Pruefe, ob gerade ein Automatikmodus-Lauf aktiv ist..."
echo "============================================"
echo "(Empfehlung: erst pruefen/warten, falls ja - ein aktiver Lauf wird durch"
echo " dieses Skript zwar NICHT unterbrochen (kein Dienst-Neustart, nur"
echo " Textdateien werden gepatcht), aber ein GERADE geschriebenes Kapitel"
echo " liest die alte Persona-Version noch bis zum naechsten Kapitel.)"
ssh -i "$KEY" "$HOST" "date -u && journalctl -u geschichten.service -n 15 --no-pager"
echo
read -p "Weitermachen? (j/n) " weiter
if [[ "$weiter" != "j" ]]; then
  echo "Abgebrochen."
  exit 0
fi

echo "============================================"
echo "1/3: Migrationsskript hochladen..."
echo "============================================"
scp -i "$KEY" backend/scripts/patch_spannungsbogen_persona.py "$HOST:$REMOTE/backend/scripts/"

echo "============================================"
echo "2/3: Epochen-Bibliothek (Vorlagen fuer neue Geschichten)..."
echo "============================================"
ssh -i "$KEY" "$HOST" "cd $REMOTE/backend && .venv/bin/python3 scripts/patch_spannungsbogen_persona.py app/data $APPLY"

echo "============================================"
echo "3/3: Bereits angelegte Geschichten..."
echo "============================================"
ssh -i "$KEY" "$HOST" "cd $REMOTE/backend && .venv/bin/python3 scripts/patch_spannungsbogen_persona.py instance/projects $APPLY"

echo
if [[ "$APPLY" != "--apply" ]]; then
  echo "Nur Dry-Run. Zum tatsaechlichen Schreiben:"
  echo "  ./deploy-spannungsbogen-persona.sh --apply"
else
  echo "Fertig."
fi
