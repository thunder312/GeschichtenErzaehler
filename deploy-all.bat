@echo off
setlocal

rem Kompletter Deploy (Backend + Frontend + Docs) fuer Geschichten Erzaehler
rem auf den Strato-Server: baut lokal, laedt hoch, tauscht auf dem Server
rem atomar aus und startet das Backend neu. Fuer nur den docs/-Ordner
rem stattdessen deploy-docs.bat verwenden.

cd /d "%~dp0"

set KEY=C:\Users\dertl\.ssh\strato_key
set HOST=root@82.165.153.177
set REMOTE=/var/www/geschichten
set TMPDIR=%~dp0deploy-tmp

if not exist "%TMPDIR%" mkdir "%TMPDIR%"

echo ============================================
echo 1/6: Frontend bauen...
echo ============================================
cd frontend
call npm run build
if errorlevel 1 (
    echo Frontend-Build fehlgeschlagen - abgebrochen.
    exit /b 1
)
cd ..

echo ============================================
echo 2/6: Backend-Tarball packen...
echo ============================================
cd backend
tar --exclude=__pycache__ --exclude=*.pyc -czf "%TMPDIR%\geschichten-backend.tar.gz" app requirements.txt scripts
if errorlevel 1 (
    echo Backend-Tarball fehlgeschlagen - abgebrochen.
    cd ..
    exit /b 1
)
cd ..

echo ============================================
echo 3/6: Backend hochladen und neu starten...
echo ============================================
scp -i "%KEY%" "%TMPDIR%\geschichten-backend.tar.gz" "%HOST%:%REMOTE%/backend/"
if errorlevel 1 (
    echo Backend-Upload fehlgeschlagen - abgebrochen.
    exit /b 1
)
rem pip install VOR dem Neustart: ohne das wuerden neu hinzugekommene
rem Abhaengigkeiten in requirements.txt beim normalen Deploy still
rem uebersehen - die Datei landete zwar mit hoch, wurde aber nie
rem tatsaechlich installiert.
ssh -i "%KEY%" %HOST% "cd %REMOTE%/backend && tar -xzf geschichten-backend.tar.gz && rm geschichten-backend.tar.gz && ./.venv/bin/pip install -q -r requirements.txt && chown -R www-data:www-data %REMOTE%/backend && systemctl restart geschichten && sleep 2 && systemctl is-active geschichten"
if errorlevel 1 (
    echo Backend-Neustart auf dem Server fehlgeschlagen.
    exit /b 1
)

echo ============================================
echo 4/6: Frontend hochladen und austauschen...
echo ============================================
scp -i "%KEY%" -r frontend\dist "%HOST%:%REMOTE%/dist_new"
if errorlevel 1 (
    echo Frontend-Upload fehlgeschlagen - abgebrochen.
    exit /b 1
)
ssh -i "%KEY%" %HOST% "rm -rf %REMOTE%/dist_alt && mv %REMOTE%/dist %REMOTE%/dist_alt && mv %REMOTE%/dist_new %REMOTE%/dist && chown -R www-data:www-data %REMOTE%/dist && rm -rf %REMOTE%/dist_alt"
if errorlevel 1 (
    echo Frontend-Austausch auf dem Server fehlgeschlagen - dist_new liegt evtl. noch auf dem Server.
    exit /b 1
)

echo ============================================
echo 5/6: Docs hochladen und austauschen...
echo ============================================
scp -i "%KEY%" -r docs "%HOST%:%REMOTE%/docs_new"
if errorlevel 1 (
    echo Docs-Upload fehlgeschlagen - abgebrochen.
    exit /b 1
)
ssh -i "%KEY%" %HOST% "rm -rf %REMOTE%/docs_alt && mv %REMOTE%/docs %REMOTE%/docs_alt && mv %REMOTE%/docs_new %REMOTE%/docs && chown -R www-data:www-data %REMOTE%/docs && rm -rf %REMOTE%/docs_alt"
if errorlevel 1 (
    echo Docs-Austausch auf dem Server fehlgeschlagen - docs_new liegt evtl. noch auf dem Server.
    exit /b 1
)

echo ============================================
echo 6/6: Verifikation...
echo ============================================
ssh -i "%KEY%" %HOST% "systemctl is-active geschichten && curl -s -o /dev/null -w 'HTTP %%{http_code}\n' https://geschichten.daniel-ertl.de/"

echo.
echo Fertig.
endlocal
