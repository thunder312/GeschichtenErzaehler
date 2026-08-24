#!/usr/bin/env bash
# Einmalige Nachruestung auf dem Strato-Server: bringt die neue "Funktion im
# Spannungsbogen"-Erklaerung (siehe backend/app/core/epoche.py, seit
# 2026-08-24 in jeder neu erzeugten Persona enthalten) BEIDES:
#   1. in die Epochen-Bibliothek (backend/app/data) - Vorlage fuer NEUE
#      Geschichten. Wird normalerweise NICHT per deploy-all.sh mitgeschickt
#      (app/data ist dort bewusst ausgeschlossen, siehe Kommentar dort), hier
#      wird deshalb gezielt nur das eine Migrationsskript hochgeladen.
#   2. in JEDE bereits angelegte Geschichte - deren Persona-Kopie wurde beim
#      Anlegen einmalig aus der Epochen-Bibliothek kopiert und aendert sich
#      seither nie von selbst. WICHTIG: Der tatsaechliche Speicherort der
#      Geschichten ist NICHT backend/instance/projects (das ist nur der
#      Programm-Default) - auf Prod liegt er per DB-Override
#      (Einstellungen > "Speicherort der Geschichten", siehe
#      app/services.py:projekte_wurzel_unskopiert) unter einem eigenen Pfad
#      MIT je einem Unterordner pro Benutzername. Dieses Skript liest den
#      tatsaechlichen Pfad und die Benutzerliste deshalb direkt aus der
#      Server-DB, statt den Pfad zu raten (Vorfall 2026-08-24: eine erste
#      Fassung zielte fest auf instance/projects, das auf Prod immer leer
#      ist - die eigentlichen Geschichten liegen unter
#      <projects_dir>/<username>/).
#
# Nutzt dafuer backend/scripts/patch_spannungsbogen_persona.py (idempotent,
# lokal bereits gegen die eigenen Vorher/Nachher-Stände verifiziert - siehe
# Session vom 2026-08-24). Ohne --apply macht dieses Skript NUR einen
# Dry-Run auf dem Server und zeigt, was sich aendern wuerde, OHNE etwas zu
# schreiben. Erst mit --apply wird tatsaechlich geschrieben.
#
# Bewusst OHNE interaktive Rueckfrage (fruehere Fassung hatte hier ein
# `read -p "Weitermachen? (j/n)"` - das liest in einer nicht-interaktiven
# "! <command>"-Ausfuehrung sofort EOF und bricht lautlos ab, OHNE dass der
# Nutzer das bemerkt, siehe Vorfall 2026-08-24: der Nutzer dachte, --apply
# sei durchgelaufen, tatsaechlich wurde ueberhaupt nichts geschrieben). Die
# eigentliche Sicherung ist stattdessen der Dry-Run-vor-Apply-Zweischritt
# unten (wie beim Python-Skript selbst) - der funktioniert auch nicht-
# interaktiv zuverlaessig.
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
echo "0/4: Automatikmodus-Status (rein informativ, KEINE Abfrage/Blockade)"
echo "============================================"
echo "Ein aktiver Lauf wird durch dieses Skript NICHT unterbrochen (kein"
echo "Dienst-Neustart, nur Textdateien werden gepatcht) - ein GERADE"
echo "geschriebenes Kapitel liest die alte Persona-Version aber noch bis zum"
echo "naechsten Kapitel. Bei Bedarf selbst abwaegen, ob du warten willst."
ssh -i "$KEY" "$HOST" "date -u && journalctl -u geschichten.service -n 15 --no-pager"

echo "============================================"
echo "1/4: Migrationsskript hochladen..."
echo "============================================"
scp -i "$KEY" backend/scripts/patch_spannungsbogen_persona.py "$HOST:$REMOTE/backend/scripts/"

echo "============================================"
echo "2/4: Epochen-Bibliothek (Vorlagen fuer neue Geschichten)..."
echo "============================================"
ssh -i "$KEY" "$HOST" "cd $REMOTE/backend && .venv/bin/python3 scripts/patch_spannungsbogen_persona.py app/data $APPLY"

echo "============================================"
echo "3/4: Tatsaechlichen Speicherort der Geschichten aus der Server-DB lesen..."
echo "============================================"
WURZELN=$(ssh -i "$KEY" "$HOST" "cd $REMOTE/backend && .venv/bin/python3 -c \"
import sqlite3
from pathlib import Path
conn = sqlite3.connect('instance/novelle_gui.db')
row = conn.execute('SELECT projects_dir FROM einstellungen WHERE id=1').fetchone()
basis = Path(row[0]) if row and row[0] else Path('instance/projects')
for (username,) in conn.execute('SELECT username FROM benutzer'):
    print(basis / username)
\"")
if [[ -z "$WURZELN" ]]; then
  echo "WARNUNG: Keine Benutzer in der Server-DB gefunden - ueberspringe Schritt 4."
else
  echo "Gefundene Wurzeln:"
  echo "$WURZELN"
fi

echo "============================================"
echo "4/4: Bereits angelegte Geschichten je Benutzer-Wurzel..."
echo "============================================"
while IFS= read -r wurzel; do
  [[ -z "$wurzel" ]] && continue
  echo "--- $wurzel ---"
  ssh -i "$KEY" "$HOST" "cd $REMOTE/backend && .venv/bin/python3 scripts/patch_spannungsbogen_persona.py \"$wurzel\" $APPLY"
done <<< "$WURZELN"

echo
if [[ "$APPLY" != "--apply" ]]; then
  echo "Nur Dry-Run. Zum tatsaechlichen Schreiben:"
  echo "  ./deploy-spannungsbogen-persona.sh --apply"
else
  echo "Fertig."
fi
