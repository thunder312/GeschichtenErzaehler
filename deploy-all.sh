#!/usr/bin/env bash
# Kompletter Deploy (Backend + Frontend + Docs) fuer Geschichten Erzaehler
# auf den Strato-Server: baut lokal, laedt hoch, tauscht auf dem Server
# atomar aus und startet das Backend neu.
set -e
cd "$(dirname "$0")"

KEY="$HOME/.ssh/strato_key"
HOST="root@82.165.153.177"
REMOTE="/var/www/geschichten"
TMPDIR="$(pwd)/deploy-tmp"
mkdir -p "$TMPDIR"

echo "============================================"
echo "1/6: Frontend bauen..."
echo "============================================"
(cd frontend && npm run build)

echo "============================================"
echo "2/6: Backend-Tarball packen..."
echo "============================================"
(cd backend && tar --exclude=__pycache__ --exclude='*.pyc' -czf "$TMPDIR/geschichten-backend.tar.gz" app requirements.txt scripts)

echo "============================================"
echo "3/6: Backend hochladen und neu starten..."
echo "============================================"
scp -i "$KEY" "$TMPDIR/geschichten-backend.tar.gz" "$HOST:$REMOTE/backend/"
ssh -i "$KEY" "$HOST" "cd $REMOTE/backend && tar -xzf geschichten-backend.tar.gz && rm geschichten-backend.tar.gz && chown -R www-data:www-data $REMOTE/backend && systemctl restart geschichten && sleep 2 && systemctl is-active geschichten"

echo "============================================"
echo "4/6: Frontend hochladen und austauschen..."
echo "============================================"
scp -i "$KEY" -r frontend/dist "$HOST:$REMOTE/dist_new"
ssh -i "$KEY" "$HOST" "rm -rf $REMOTE/dist_alt && mv $REMOTE/dist $REMOTE/dist_alt && mv $REMOTE/dist_new $REMOTE/dist && chown -R www-data:www-data $REMOTE/dist && rm -rf $REMOTE/dist_alt"

echo "============================================"
echo "5/6: Docs hochladen und austauschen..."
echo "============================================"
scp -i "$KEY" -r docs "$HOST:$REMOTE/docs_new"
ssh -i "$KEY" "$HOST" "rm -rf $REMOTE/docs_alt && mv $REMOTE/docs $REMOTE/docs_alt && mv $REMOTE/docs_new $REMOTE/docs && chown -R www-data:www-data $REMOTE/docs && rm -rf $REMOTE/docs_alt"

echo "============================================"
echo "6/6: Verifikation..."
echo "============================================"
ssh -i "$KEY" "$HOST" "systemctl is-active geschichten && curl -s -o /dev/null -w 'HTTP %{http_code}\n' https://geschichten.daniel-ertl.de/"

echo
echo "Fertig."
